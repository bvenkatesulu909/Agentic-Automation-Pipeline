import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)


@dataclass
class Instruction:
    """Single instruction sample."""

    instruction: str
    input: str
    output: str
    system_prompt: Optional[str] = None


class InstructionDataset(Dataset):
    """PyTorch Dataset for instruction-following tasks."""

    def __init__(
        self,
        samples: List[Dict],
        tokenizer,
        max_length: int = 512,
    ):
        self.samples = samples
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.samples[idx]
        text = self._format_sample(sample)

        encodings = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        return {
            "input_ids": encodings["input_ids"].squeeze(),
            "attention_mask": encodings["attention_mask"].squeeze(),
            "labels": encodings["input_ids"].squeeze(),
        }

    def _format_sample(self, sample: Dict) -> str:
        """Format instruction sample into model input."""
        instruction = sample.get("instruction", "")
        input_text = sample.get("input", "")
        output = sample.get("output", "")
        system_prompt = sample.get("system_prompt", "You are a helpful assistant.")

        if input_text:
            prompt = f"{system_prompt}\n\n### Instruction:\n{instruction}\n\n### Input:\n{input_text}\n\n### Output:\n{output}"
        else:
            prompt = f"{system_prompt}\n\n### Instruction:\n{instruction}\n\n### Output:\n{output}"

        return prompt


class DPODataset(Dataset):
    """Dataset for Direct Preference Optimization."""

    def __init__(
        self,
        samples: List[Dict],
        tokenizer,
        max_length: int = 512,
    ):
        self.samples = samples
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        sample = self.samples[idx]

        prompt = sample.get("prompt", "")
        chosen = sample.get("chosen", "")
        rejected = sample.get("rejected", "")

        chosen_text = f"{prompt}\n{chosen}"
        rejected_text = f"{prompt}\n{rejected}"

        chosen_encodings = self.tokenizer(
            chosen_text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        rejected_encodings = self.tokenizer(
            rejected_text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        return {
            "prompt_input_ids": chosen_encodings["input_ids"].squeeze(),
            "prompt_attention_mask": chosen_encodings["attention_mask"].squeeze(),
            "chosen_input_ids": chosen_encodings["input_ids"].squeeze(),
            "chosen_attention_mask": chosen_encodings["attention_mask"].squeeze(),
            "rejected_input_ids": rejected_encodings["input_ids"].squeeze(),
            "rejected_attention_mask": rejected_encodings["attention_mask"].squeeze(),
        }


class DatasetPreparator:
    """Prepare and manage datasets for fine-tuning."""

    def __init__(self, tokenizer_name: str = "meta-llama/Llama-2-7b-hf"):
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def load_jsonl(self, path: str) -> List[Dict]:
        """Load JSONL dataset."""
        samples = []
        with open(path, "r") as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
        logger.info(f"Loaded {len(samples)} samples from {path}")
        return samples

    def load_json(self, path: str) -> List[Dict]:
        """Load JSON dataset."""
        with open(path, "r") as f:
            samples = json.load(f)
        logger.info(f"Loaded {len(samples)} samples from {path}")
        return samples

    def validate_instruction_format(self, samples: List[Dict]) -> bool:
        """Validate instruction dataset format."""
        required_fields = {"instruction", "output"}
        optional_fields = {"input", "system_prompt"}

        for i, sample in enumerate(samples):
            if not required_fields.issubset(sample.keys()):
                logger.error(
                    f"Sample {i} missing required fields: {required_fields - set(sample.keys())}"
                )
                return False

            invalid_keys = set(sample.keys()) - required_fields - optional_fields
            if invalid_keys:
                logger.warning(f"Sample {i} has unexpected fields: {invalid_keys}")

        return True

    def validate_dpo_format(self, samples: List[Dict]) -> bool:
        """Validate DPO dataset format."""
        required_fields = {"prompt", "chosen", "rejected"}

        for i, sample in enumerate(samples):
            if not required_fields.issubset(sample.keys()):
                logger.error(
                    f"Sample {i} missing required fields: {required_fields - set(sample.keys())}"
                )
                return False

        return True

    def split_dataset(
        self, samples: List[Dict], train_ratio: float = 0.8
    ) -> Tuple[List[Dict], List[Dict]]:
        """Split dataset into train and eval sets."""
        split_idx = int(len(samples) * train_ratio)
        train_samples = samples[:split_idx]
        eval_samples = samples[split_idx:]
        logger.info(
            f"Split dataset: {len(train_samples)} train, {len(eval_samples)} eval"
        )
        return train_samples, eval_samples

    def prepare_instruction_dataset(
        self,
        samples: List[Dict],
        max_length: int = 512,
        train_ratio: float = 0.8,
    ) -> Tuple[InstructionDataset, InstructionDataset]:
        """Prepare instruction dataset."""
        if not self.validate_instruction_format(samples):
            raise ValueError("Invalid instruction dataset format")

        train_samples, eval_samples = self.split_dataset(samples, train_ratio)

        train_dataset = InstructionDataset(
            train_samples, self.tokenizer, max_length=max_length
        )
        eval_dataset = InstructionDataset(
            eval_samples, self.tokenizer, max_length=max_length
        )

        logger.info(
            f"Prepared instruction dataset: {len(train_dataset)} train, {len(eval_dataset)} eval"
        )
        return train_dataset, eval_dataset

    def prepare_dpo_dataset(
        self,
        samples: List[Dict],
        max_length: int = 512,
        train_ratio: float = 0.8,
    ) -> Tuple[DPODataset, DPODataset]:
        """Prepare DPO dataset."""
        if not self.validate_dpo_format(samples):
            raise ValueError("Invalid DPO dataset format")

        train_samples, eval_samples = self.split_dataset(samples, train_ratio)

        train_dataset = DPODataset(
            train_samples, self.tokenizer, max_length=max_length
        )
        eval_dataset = DPODataset(
            eval_samples, self.tokenizer, max_length=max_length
        )

        logger.info(
            f"Prepared DPO dataset: {len(train_dataset)} train, {len(eval_dataset)} eval"
        )
        return train_dataset, eval_dataset

    def create_golden_set(
        self, samples: List[Dict], ratio: float = 0.05
    ) -> List[Dict]:
        """Create golden set for catastrophic forgetting detection."""
        golden_count = max(1, int(len(samples) * ratio))
        golden_set = samples[:golden_count]
        logger.info(f"Created golden set with {len(golden_set)} samples")
        return golden_set
