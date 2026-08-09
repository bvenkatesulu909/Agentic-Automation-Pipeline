import json
import logging
from pathlib import Path
from typing import Dict, Optional, List

import torch

from .config import FineTuningConfig, TrainingArgs
from .dataset import DatasetPreparator
from .trainer import LoRAInstructionTuner, DPOTrainer
from .evaluator import ModelEvaluator, CatastrophicForgettingDetector

logger = logging.getLogger(__name__)


class FineTuningPipeline:
    """End-to-end fine-tuning pipeline."""

    def __init__(
        self,
        model_name: str,
        output_dir: str = "./outputs",
        lora_config: Optional[FineTuningConfig] = None,
        training_args: Optional[TrainingArgs] = None,
    ):
        self.model_name = model_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.lora_config = lora_config or FineTuningConfig(model_name=model_name)
        self.training_args = training_args or TrainingArgs()

        self.dataset_preparator = DatasetPreparator(model_name)
        self.evaluator = ModelEvaluator(model_name)
        self.forgetting_detector = CatastrophicForgettingDetector(model_name)

        logger.info(f"Pipeline initialized with model: {model_name}")

    def run_instruction_tuning(
        self,
        instruction_data_path: str,
        benchmark_data_path: Optional[str] = None,
        use_golden_set: bool = True,
    ) -> Dict:
        """Run instruction tuning phase."""
        logger.info("Starting instruction tuning phase...")

        samples = self.dataset_preparator.load_jsonl(instruction_data_path)
        train_dataset, eval_dataset = self.dataset_preparator.prepare_instruction_dataset(
            samples
        )

        golden_set = None
        if use_golden_set:
            golden_set = self.dataset_preparator.create_golden_set(samples)
            logger.info(f"Created golden set with {len(golden_set)} samples")

        trainer = LoRAInstructionTuner(self.lora_config, self.training_args)

        training_result = trainer.train(train_dataset, eval_dataset, golden_set)

        output_dir = self.output_dir / "instruction_tuning"
        trainer.save(str(output_dir))

        logger.info(f"Instruction tuning complete. Saved to {output_dir}")

        result = {
            "phase": "instruction_tuning",
            "output_dir": str(output_dir),
            "training_result": training_result,
        }

        if benchmark_data_path:
            logger.info("Running benchmark evaluation...")
            benchmark_samples = self.dataset_preparator.load_jsonl(benchmark_data_path)
            benchmark_result = self.evaluator.evaluate_on_benchmark(
                trainer.model, benchmark_samples
            )
            result["benchmark"] = benchmark_result

        return result

    def run_dpo_alignment(
        self,
        dpo_data_path: str,
        pretrained_adapter_path: Optional[str] = None,
    ) -> Dict:
        """Run DPO alignment phase."""
        logger.info("Starting DPO alignment phase...")

        samples = self.dataset_preparator.load_jsonl(dpo_data_path)
        train_dataset, eval_dataset = self.dataset_preparator.prepare_dpo_dataset(
            samples
        )

        trainer = DPOTrainer(
            self.model_name,
            self.training_args,
            lora_config=self.lora_config,
        )

        if pretrained_adapter_path:
            logger.info(f"Loading pretrained adapter from {pretrained_adapter_path}")

        trainer.train(train_dataset, eval_dataset)

        output_dir = self.output_dir / "dpo_alignment"
        trainer.save(str(output_dir))

        logger.info(f"DPO alignment complete. Saved to {output_dir}")

        return {
            "phase": "dpo_alignment",
            "output_dir": str(output_dir),
        }

    def evaluate_catastrophic_forgetting(
        self,
        instruction_tuning_path: str,
        golden_set_path: str,
        threshold: float = 0.7,
    ) -> Dict:
        """Evaluate catastrophic forgetting."""
        logger.info("Evaluating catastrophic forgetting...")

        golden_set = self.dataset_preparator.load_jsonl(golden_set_path)

        from transformers import AutoModelForCausalLM
        from peft import PeftModel

        model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        model = PeftModel.from_pretrained(model, instruction_tuning_path)

        is_forgetting, distance = self.forgetting_detector.detect_forgetting(
            model, golden_set, threshold=threshold
        )

        fisher_info = self.forgetting_detector.compute_fisher_information(
            model, golden_set
        )

        result = {
            "is_catastrophic_forgetting": is_forgetting,
            "embedding_distance": distance,
            "threshold": threshold,
            "fisher_info_keys": list(fisher_info.keys()),
        }

        return result

    def run_before_after_evaluation(
        self,
        benchmark_data_path: str,
        finetuned_adapter_path: str,
    ) -> Dict:
        """Compare base and fine-tuned models."""
        logger.info("Running before/after evaluation...")

        benchmark_samples = self.dataset_preparator.load_jsonl(benchmark_data_path)

        comparison = self.evaluator.compare_models(
            None,
            finetuned_adapter_path,
            benchmark_samples,
        )

        logger.info("Before/after evaluation complete")

        return comparison

    def save_config(self):
        """Save pipeline configuration."""
        config = {
            "model_name": self.model_name,
            "lora_config": {
                "r": self.lora_config.lora_r,
                "alpha": self.lora_config.lora_alpha,
                "dropout": self.lora_config.lora_dropout,
                "target_modules": self.lora_config.target_modules,
            },
            "training_args": {
                "num_epochs": self.training_args.num_train_epochs,
                "batch_size": self.training_args.per_device_train_batch_size,
                "learning_rate": self.training_args.learning_rate,
            },
        }

        config_path = self.output_dir / "pipeline_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Config saved to {config_path}")

    def load_checkpoint(self, checkpoint_path: str):
        """Load from checkpoint."""
        logger.info(f"Loading checkpoint from {checkpoint_path}")

        checkpoint_dir = Path(checkpoint_path)
        if (checkpoint_dir / "pipeline_config.json").exists():
            with open(checkpoint_dir / "pipeline_config.json") as f:
                config = json.load(f)
                logger.info(f"Loaded config: {config}")

        return checkpoint_dir
