from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class FineTuningConfig:
    """Configuration for LoRA fine-tuning."""

    model_name: str
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: ["q_proj", "v_proj"])
    task_type: str = "CAUSAL_LM"
    bias: str = "none"
    inference_mode: bool = False


@dataclass
class TrainingArgs:
    """Training arguments for instruction tuning and DPO."""

    output_dir: str = "./outputs"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    per_device_eval_batch_size: int = 8
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_steps: int = 100
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0

    logging_steps: int = 10
    eval_steps: int = 100
    save_steps: int = 100
    save_total_limit: int = 3

    bf16: bool = True
    tf32: bool = True
    logging_dir: str = "./logs"
    seed: int = 42

    # DPO specific
    beta: float = 0.1
    loss_type: str = "sigmoid"

    # Catastrophic forgetting prevention
    regularization_weight: float = 0.1
    freeze_base_layers: bool = False
    eval_set_size: float = 0.1
