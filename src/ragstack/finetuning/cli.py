import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from .pipeline import FineTuningPipeline
from .config import FineTuningConfig, TrainingArgs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_instruction_tuning_parser(subparsers):
    """Create parser for instruction tuning."""
    parser = subparsers.add_parser(
        "instruction-tuning",
        help="Run instruction tuning with LoRA",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model name (e.g., meta-llama/Llama-2-7b-hf)",
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to instruction dataset (JSONL format)",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        help="Path to benchmark dataset for evaluation",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./outputs",
        help="Output directory",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Training batch size",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="Learning rate",
    )
    parser.add_argument(
        "--lora-r",
        type=int,
        default=8,
        help="LoRA rank",
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=16,
        help="LoRA alpha",
    )
    parser.add_argument(
        "--no-golden-set",
        action="store_true",
        help="Don't create golden set for forgetting detection",
    )
    parser.set_defaults(func=run_instruction_tuning)


def create_dpo_parser(subparsers):
    """Create parser for DPO alignment."""
    parser = subparsers.add_parser(
        "dpo-alignment",
        help="Run DPO alignment",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Base model name",
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to DPO dataset (JSONL format)",
    )
    parser.add_argument(
        "--adapter",
        type=str,
        help="Path to pretrained LoRA adapter (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./outputs",
        help="Output directory",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Training batch size",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=0.1,
        help="DPO beta parameter",
    )
    parser.set_defaults(func=run_dpo_alignment)


def create_eval_parser(subparsers):
    """Create parser for evaluation."""
    parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate model before/after fine-tuning",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Base model name",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        help="Path to benchmark dataset (JSONL format)",
    )
    parser.add_argument(
        "--adapter",
        type=str,
        required=True,
        help="Path to LoRA adapter for comparison",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./outputs",
        help="Output directory",
    )
    parser.set_defaults(func=run_evaluation)


def create_forgetting_parser(subparsers):
    """Create parser for catastrophic forgetting detection."""
    parser = subparsers.add_parser(
        "detect-forgetting",
        help="Detect catastrophic forgetting",
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Base model name",
    )
    parser.add_argument(
        "--adapter",
        type=str,
        required=True,
        help="Path to fine-tuned adapter",
    )
    parser.add_argument(
        "--golden-set",
        type=str,
        required=True,
        help="Path to golden set (JSONL format)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Forgetting threshold",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./outputs",
        help="Output directory",
    )
    parser.set_defaults(func=run_forgetting_detection)


def run_instruction_tuning(args):
    """Run instruction tuning."""
    lora_config = FineTuningConfig(
        model_name=args.model,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
    )

    training_args = TrainingArgs(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )

    pipeline = FineTuningPipeline(
        args.model,
        output_dir=args.output,
        lora_config=lora_config,
        training_args=training_args,
    )

    result = pipeline.run_instruction_tuning(
        args.data,
        benchmark_data_path=args.benchmark,
        use_golden_set=not args.no_golden_set,
    )

    pipeline.save_config()

    with open(Path(args.output) / "instruction_tuning_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Results saved to {args.output}")


def run_dpo_alignment(args):
    """Run DPO alignment."""
    lora_config = FineTuningConfig(model_name=args.model)

    training_args = TrainingArgs(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        beta=args.beta,
    )

    pipeline = FineTuningPipeline(
        args.model,
        output_dir=args.output,
        lora_config=lora_config,
        training_args=training_args,
    )

    result = pipeline.run_dpo_alignment(
        args.data,
        pretrained_adapter_path=args.adapter,
    )

    with open(Path(args.output) / "dpo_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Results saved to {args.output}")


def run_evaluation(args):
    """Run before/after evaluation."""
    pipeline = FineTuningPipeline(args.model, output_dir=args.output)

    result = pipeline.run_before_after_evaluation(
        args.benchmark,
        args.adapter,
    )

    with open(Path(args.output) / "evaluation_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Evaluation results saved to {args.output}")


def run_forgetting_detection(args):
    """Run catastrophic forgetting detection."""
    pipeline = FineTuningPipeline(args.model, output_dir=args.output)

    result = pipeline.evaluate_catastrophic_forgetting(
        args.adapter,
        args.golden_set,
        threshold=args.threshold,
    )

    with open(Path(args.output) / "forgetting_detection.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    logger.info(f"Forgetting detection results saved to {args.output}")


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="LoRA Fine-Tuning Pipeline with DPO and Catastrophic Forgetting Detection",
    )

    subparsers = parser.add_subparsers(title="commands", dest="command")

    create_instruction_tuning_parser(subparsers)
    create_dpo_parser(subparsers)
    create_eval_parser(subparsers)
    create_forgetting_parser(subparsers)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
