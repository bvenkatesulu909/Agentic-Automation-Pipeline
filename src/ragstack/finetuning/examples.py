"""
Example usage of the Fine-Tuning Pipeline.
"""

import json
import logging
from pathlib import Path

from .pipeline import FineTuningPipeline
from .config import FineTuningConfig, TrainingArgs
from .dataset import DatasetPreparator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sample_instruction_data():
    """Create sample instruction dataset."""
    samples = [
        {
            "instruction": "Summarize the following text",
            "input": "The quick brown fox jumps over the lazy dog. This is a common phrase used in typography.",
            "output": "A quick brown fox jumps over a lazy dog. This phrase is often used in typography testing.",
            "system_prompt": "You are a helpful assistant that summarizes text.",
        },
        {
            "instruction": "Translate to Spanish",
            "input": "Hello, how are you?",
            "output": "Hola, ¿cómo estás?",
            "system_prompt": "You are a helpful translator.",
        },
        {
            "instruction": "Answer the following question",
            "input": "What is 2 + 2?",
            "output": "2 + 2 equals 4.",
            "system_prompt": "You are a helpful math assistant.",
        },
        {
            "instruction": "Write a haiku",
            "input": "about nature",
            "output": "Trees sway in the wind\nBirds sing at dawn's light\nNature breathes and lives",
            "system_prompt": "You are a creative poet.",
        },
        {
            "instruction": "Explain a concept",
            "input": "What is machine learning?",
            "output": "Machine learning is a subset of artificial intelligence where systems learn patterns from data without explicit programming.",
            "system_prompt": "You are an educational expert.",
        },
    ]

    output_path = Path("./sample_data/instruction_data.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    logger.info(f"Created sample instruction data at {output_path}")
    return str(output_path)


def create_sample_dpo_data():
    """Create sample DPO dataset."""
    samples = [
        {
            "prompt": "Summarize this: The quick brown fox jumps over the lazy dog.",
            "chosen": "A quick brown fox jumps over a lazy dog.",
            "rejected": "The fox is brown and quick. It jumps. There is a dog.",
        },
        {
            "prompt": "Translate to Spanish: Hello",
            "chosen": "Hola",
            "rejected": "Hello in Spanish is... um... saludos?",
        },
        {
            "prompt": "What is 2 + 2?",
            "chosen": "2 + 2 equals 4.",
            "rejected": "2 + 2 is probably around 5 or something.",
        },
        {
            "prompt": "Explain quantum computing",
            "chosen": "Quantum computing uses quantum bits (qubits) that can exist in superposition, allowing for parallel computation.",
            "rejected": "Quantum computing is like regular computers but... quantum.",
        },
        {
            "prompt": "Write a short poem",
            "chosen": "Moonlight dances on the lake,\nSilent ripples gently wake,\nNature's beauty on display.",
            "rejected": "Moon is bright. Water has moon. Nice.",
        },
    ]

    output_path = Path("./sample_data/dpo_data.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    logger.info(f"Created sample DPO data at {output_path}")
    return str(output_path)


def create_sample_benchmark():
    """Create sample benchmark dataset."""
    samples = [
        {
            "prompt": "Summarize: The Eiffel Tower is a wrought-iron lattice tower in Paris.",
            "expected_output": "The Eiffel Tower is a wrought-iron lattice tower located in Paris.",
            "keywords": ["Eiffel Tower", "Paris", "wrought-iron"],
        },
        {
            "prompt": "Translate to Spanish: Thank you very much",
            "expected_output": "Muchas gracias",
            "keywords": ["gracias"],
        },
        {
            "prompt": "What are the main types of machine learning?",
            "expected_output": "The main types are supervised learning, unsupervised learning, and reinforcement learning.",
            "keywords": ["supervised", "unsupervised", "reinforcement"],
        },
    ]

    output_path = Path("./sample_data/benchmark.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    logger.info(f"Created sample benchmark at {output_path}")
    return str(output_path)


def example_instruction_tuning():
    """Example: Run instruction tuning."""
    logger.info("=" * 60)
    logger.info("EXAMPLE: Instruction Tuning with LoRA")
    logger.info("=" * 60)

    instruction_data = create_sample_instruction_data()
    benchmark_data = create_sample_benchmark()

    lora_config = FineTuningConfig(
        model_name="meta-llama/Llama-2-7b-hf",
        lora_r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )

    training_args = TrainingArgs(
        output_dir="./outputs/instruction_tuning",
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_steps=100,
        eval_steps=10,
        save_steps=10,
    )

    pipeline = FineTuningPipeline(
        "meta-llama/Llama-2-7b-hf",
        output_dir="./outputs",
        lora_config=lora_config,
        training_args=training_args,
    )

    result = pipeline.run_instruction_tuning(
        instruction_data,
        benchmark_data_path=benchmark_data,
        use_golden_set=True,
    )

    pipeline.save_config()

    logger.info(f"Instruction tuning complete!")
    logger.info(f"Result: {json.dumps(result, indent=2, default=str)}")

    return str(Path("./outputs/instruction_tuning"))


def example_dpo_alignment():
    """Example: Run DPO alignment."""
    logger.info("=" * 60)
    logger.info("EXAMPLE: DPO Alignment")
    logger.info("=" * 60)

    dpo_data = create_sample_dpo_data()

    lora_config = FineTuningConfig(
        model_name="meta-llama/Llama-2-7b-hf",
    )

    training_args = TrainingArgs(
        output_dir="./outputs/dpo_alignment",
        num_train_epochs=1,
        per_device_train_batch_size=4,
        learning_rate=1e-4,
        beta=0.1,
        loss_type="sigmoid",
    )

    pipeline = FineTuningPipeline(
        "meta-llama/Llama-2-7b-hf",
        output_dir="./outputs",
        lora_config=lora_config,
        training_args=training_args,
    )

    result = pipeline.run_dpo_alignment(dpo_data)

    logger.info(f"DPO alignment complete!")
    logger.info(f"Result: {json.dumps(result, indent=2, default=str)}")

    return str(Path("./outputs/dpo_alignment"))


def example_catastrophic_forgetting_detection():
    """Example: Detect catastrophic forgetting."""
    logger.info("=" * 60)
    logger.info("EXAMPLE: Catastrophic Forgetting Detection")
    logger.info("=" * 60)

    instruction_data = create_sample_instruction_data()
    golden_set = Path("./sample_data/golden_set.jsonl")
    golden_set.parent.mkdir(parents=True, exist_ok=True)

    preparator = DatasetPreparator("meta-llama/Llama-2-7b-hf")
    samples = preparator.load_jsonl(str(instruction_data))
    golden = preparator.create_golden_set(samples, ratio=0.3)

    with open(golden_set, "w") as f:
        for sample in golden:
            f.write(json.dumps(sample) + "\n")

    pipeline = FineTuningPipeline(
        "meta-llama/Llama-2-7b-hf",
        output_dir="./outputs",
    )

    adapter_path = "./outputs/instruction_tuning/lora_adapters"

    result = pipeline.evaluate_catastrophic_forgetting(
        adapter_path,
        str(golden_set),
        threshold=0.7,
    )

    logger.info(f"Catastrophic forgetting detection complete!")
    logger.info(f"Result: {json.dumps(result, indent=2, default=str)}")

    return result


def example_before_after_evaluation():
    """Example: Before/after evaluation."""
    logger.info("=" * 60)
    logger.info("EXAMPLE: Before/After Evaluation")
    logger.info("=" * 60)

    benchmark_data = create_sample_benchmark()

    pipeline = FineTuningPipeline(
        "meta-llama/Llama-2-7b-hf",
        output_dir="./outputs",
    )

    adapter_path = "./outputs/instruction_tuning/lora_adapters"

    result = pipeline.run_before_after_evaluation(
        benchmark_data,
        adapter_path,
    )

    logger.info(f"Before/after evaluation complete!")
    logger.info(f"Result: {json.dumps(result, indent=2, default=str)}")

    return result


def example_end_to_end_pipeline():
    """Example: Complete end-to-end pipeline."""
    logger.info("=" * 60)
    logger.info("EXAMPLE: End-to-End Fine-Tuning Pipeline")
    logger.info("=" * 60)

    instruction_data = create_sample_instruction_data()
    dpo_data = create_sample_dpo_data()
    benchmark_data = create_sample_benchmark()

    lora_config = FineTuningConfig(
        model_name="meta-llama/Llama-2-7b-hf",
        lora_r=8,
        lora_alpha=16,
    )

    training_args = TrainingArgs(
        output_dir="./outputs/end_to_end",
        num_train_epochs=2,
        per_device_train_batch_size=4,
        learning_rate=2e-4,
    )

    pipeline = FineTuningPipeline(
        "meta-llama/Llama-2-7b-hf",
        output_dir="./outputs/end_to_end",
        lora_config=lora_config,
        training_args=training_args,
    )

    logger.info("Step 1: Running instruction tuning...")
    instruction_result = pipeline.run_instruction_tuning(
        instruction_data,
        benchmark_data_path=benchmark_data,
        use_golden_set=True,
    )

    logger.info("Step 2: Running DPO alignment...")
    dpo_result = pipeline.run_dpo_alignment(dpo_data)

    logger.info("Step 3: Detecting catastrophic forgetting...")
    forgetting_result = pipeline.evaluate_catastrophic_forgetting(
        "./outputs/end_to_end/instruction_tuning/lora_adapters",
        "./sample_data/instruction_data.jsonl",
    )

    logger.info("Step 4: Running before/after evaluation...")
    evaluation_result = pipeline.run_before_after_evaluation(
        benchmark_data,
        "./outputs/end_to_end/dpo_alignment/model",
    )

    pipeline.save_config()

    logger.info("=" * 60)
    logger.info("END-TO-END PIPELINE COMPLETE!")
    logger.info("=" * 60)

    return {
        "instruction_tuning": instruction_result,
        "dpo_alignment": dpo_result,
        "catastrophic_forgetting": forgetting_result,
        "evaluation": evaluation_result,
    }


if __name__ == "__main__":
    logger.info("Running fine-tuning pipeline examples...")

    logger.info("\nNote: These examples use synthetic data for demonstration.")
    logger.info("For production use, replace with your actual datasets.")
