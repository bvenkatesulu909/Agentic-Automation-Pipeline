import logging
from pathlib import Path
from typing import Optional, Tuple, Dict

import torch
import torch.nn.functional as F
from torch import nn
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import get_peft_model, LoraConfig, TaskType
from tqdm import tqdm

from .config import FineTuningConfig, TrainingArgs
from .dataset import InstructionDataset, DPODataset

logger = logging.getLogger(__name__)


class LoRAInstructionTuner:
    """Instruction tuning with LoRA."""

    def __init__(self, config: FineTuningConfig, training_args: TrainingArgs):
        self.config = config
        self.training_args = training_args

        self.model = self._load_model()
        self.tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def _load_model(self):
        """Load base model with LoRA adapters."""
        model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )

        lora_config = LoraConfig(
            r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            lora_dropout=self.config.lora_dropout,
            target_modules=self.config.target_modules,
            bias=self.config.bias,
            task_type=TaskType.CAUSAL_LM,
            inference_mode=self.config.inference_mode,
        )

        model = get_peft_model(model, lora_config)
        logger.info(f"LoRA model loaded. Trainable params: {self._count_params(model)}")
        return model

    def _count_params(self, model: nn.Module) -> int:
        """Count trainable parameters."""
        return sum(p.numel() for p in model.parameters() if p.requires_grad)

    def train(
        self,
        train_dataset: InstructionDataset,
        eval_dataset: InstructionDataset,
        golden_set: Optional[InstructionDataset] = None,
    ) -> Dict:
        """Train with instruction tuning."""
        training_args = TrainingArguments(
            output_dir=self.training_args.output_dir,
            num_train_epochs=self.training_args.num_train_epochs,
            per_device_train_batch_size=self.training_args.per_device_train_batch_size,
            per_device_eval_batch_size=self.training_args.per_device_eval_batch_size,
            gradient_accumulation_steps=self.training_args.gradient_accumulation_steps,
            learning_rate=self.training_args.learning_rate,
            warmup_steps=self.training_args.warmup_steps,
            weight_decay=self.training_args.weight_decay,
            max_grad_norm=self.training_args.max_grad_norm,
            logging_steps=self.training_args.logging_steps,
            eval_strategy="steps",
            eval_steps=self.training_args.eval_steps,
            save_steps=self.training_args.save_steps,
            save_total_limit=self.training_args.save_total_limit,
            bf16=self.training_args.bf16,
            tf32=self.training_args.tf32,
            logging_dir=self.training_args.logging_dir,
            seed=self.training_args.seed,
            report_to=["tensorboard"],
            remove_unused_columns=False,
        )

        data_collator = DataCollatorForLanguageModeling(
            self.tokenizer, mlm=False
        )

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            data_collator=data_collator,
            callbacks=[],
        )

        result = trainer.train()
        logger.info(f"Training complete. Loss: {result.training_loss}")

        return result.__dict__

    def save(self, output_dir: str):
        """Save LoRA adapters."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        self.model.save_pretrained(output_path / "lora_adapters")
        self.tokenizer.save_pretrained(output_path / "tokenizer")
        logger.info(f"Model saved to {output_dir}")

    def load(self, output_dir: str):
        """Load saved LoRA adapters."""
        self.model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )

        from peft import PeftModel

        self.model = PeftModel.from_pretrained(
            self.model, Path(output_dir) / "lora_adapters"
        )
        logger.info(f"Model loaded from {output_dir}")


class DPOTrainer:
    """Direct Preference Optimization trainer."""

    def __init__(
        self,
        model_name: str,
        training_args: TrainingArgs,
        lora_config: Optional[FineTuningConfig] = None,
    ):
        self.model_name = model_name
        self.training_args = training_args
        self.lora_config = lora_config

        self.model = self._load_model()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def _load_model(self):
        """Load model with optional LoRA."""
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )

        if self.lora_config:
            lora_config = LoraConfig(
                r=self.lora_config.lora_r,
                lora_alpha=self.lora_config.lora_alpha,
                lora_dropout=self.lora_config.lora_dropout,
                target_modules=self.lora_config.target_modules,
                bias=self.lora_config.bias,
                task_type=TaskType.CAUSAL_LM,
            )
            model = get_peft_model(model, lora_config)

        return model

    def dpo_loss(
        self,
        chosen_logits: torch.Tensor,
        rejected_logits: torch.Tensor,
        beta: float = 0.1,
        loss_type: str = "sigmoid",
    ) -> torch.Tensor:
        """Compute DPO loss."""
        chosen_log_probs = F.log_softmax(chosen_logits, dim=-1)
        rejected_log_probs = F.log_softmax(rejected_logits, dim=-1)

        chosen_loss = -chosen_log_probs.mean()
        rejected_loss = -rejected_log_probs.mean()

        log_probs_diff = chosen_loss - rejected_loss

        if loss_type == "sigmoid":
            loss = -F.logsigmoid(beta * log_probs_diff).mean()
        elif loss_type == "hinge":
            loss = torch.clamp(1.0 - beta * log_probs_diff, min=0.0).mean()
        else:
            raise ValueError(f"Unknown loss type: {loss_type}")

        return loss

    def train(
        self,
        train_dataset: DPODataset,
        eval_dataset: DPODataset,
    ):
        """Train with DPO."""
        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.training_args.learning_rate,
        )

        device = next(self.model.parameters()).device

        for epoch in range(self.training_args.num_train_epochs):
            self.model.train()
            total_loss = 0

            progress_bar = tqdm(
                range(len(train_dataset)),
                desc=f"Epoch {epoch + 1}",
            )

            for step, batch in enumerate(train_dataset):
                batch = {
                    k: v.to(device) if isinstance(v, torch.Tensor) else v
                    for k, v in batch.items()
                }

                with self.model.enable_input_require_grads():
                    chosen_outputs = self.model(
                        input_ids=batch["chosen_input_ids"].unsqueeze(0),
                        attention_mask=batch["chosen_attention_mask"].unsqueeze(0),
                    )
                    rejected_outputs = self.model(
                        input_ids=batch["rejected_input_ids"].unsqueeze(0),
                        attention_mask=batch["rejected_attention_mask"].unsqueeze(0),
                    )

                    loss = self.dpo_loss(
                        chosen_outputs.logits,
                        rejected_outputs.logits,
                        beta=self.training_args.beta,
                        loss_type=self.training_args.loss_type,
                    )

                    loss = loss / self.training_args.gradient_accumulation_steps
                    loss.backward()

                if (step + 1) % self.training_args.gradient_accumulation_steps == 0:
                    optimizer.step()
                    optimizer.zero_grad()

                total_loss += loss.item()
                progress_bar.update(1)

                if step % self.training_args.logging_steps == 0:
                    avg_loss = total_loss / (step + 1)
                    logger.info(f"Step {step}, Loss: {avg_loss:.4f}")

            logger.info(f"Epoch {epoch + 1} complete. Avg Loss: {total_loss / len(train_dataset):.4f}")

    def save(self, output_dir: str):
        """Save DPO model."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        if hasattr(self.model, "save_pretrained"):
            self.model.save_pretrained(output_path / "model")
        self.tokenizer.save_pretrained(output_path / "tokenizer")
        logger.info(f"DPO model saved to {output_dir}")
