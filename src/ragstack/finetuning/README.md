# LoRA Fine-Tuning Pipeline

**Production-ready fine-tuning pipeline with LoRA, DPO, and catastrophic forgetting prevention.**

## Overview

This module provides a comprehensive framework for efficient LLM fine-tuning:

- **LoRA Adapters** - Train 0.1-1% of model parameters instead of all weights
- **Instruction Tuning** - Supervised fine-tuning on custom instruction datasets
- **DPO Alignment** - Direct Preference Optimization without reward models
- **Catastrophic Forgetting Prevention** - Multiple strategies to preserve base model knowledge
- **Before/After Evaluation** - Automatic benchmarking and comparison
- **CLI & Python API** - Both command-line and programmatic interfaces

## Quick Start

### Installation

```bash
pip install -r ../../requirements-finetuning.txt
```

### Basic Usage

```python
from src.ragstack.finetuning import FineTuningPipeline, FineTuningConfig, TrainingArgs

# Configure
config = FineTuningConfig(model_name="meta-llama/Llama-2-7b-hf", lora_r=8)
args = TrainingArgs(num_train_epochs=3, per_device_train_batch_size=4)

# Create pipeline
pipeline = FineTuningPipeline(
    "meta-llama/Llama-2-7b-hf",
    lora_config=config,
    training_args=args
)

# Run instruction tuning
result = pipeline.run_instruction_tuning("data/instructions.jsonl")
```

## Module Structure

### Core Components

| Component | Purpose |
|-----------|---------|
| **config.py** | FineTuningConfig and TrainingArgs dataclasses |
| **dataset.py** | Data loading, validation, and preparation |
| **trainer.py** | LoRA and DPO training implementations |
| **evaluator.py** | Model evaluation and forgetting detection |
| **pipeline.py** | End-to-end pipeline orchestration |
| **cli.py** | Command-line interface |
| **examples.py** | Usage examples and demonstrations |

### Data Classes

#### FineTuningConfig
```python
FineTuningConfig(
    model_name: str              # Base model to fine-tune
    lora_r: int = 8              # LoRA rank (lower = fewer params)
    lora_alpha: int = 16         # LoRA scaling factor
    lora_dropout: float = 0.05   # Dropout in LoRA layers
    target_modules: List[str]    # Which modules to adapt
    task_type: str = "CAUSAL_LM" # Task type (e.g., language modeling)
    bias: str = "none"           # How to handle bias
)
```

#### TrainingArgs
```python
TrainingArgs(
    output_dir: str = "./outputs"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    warmup_steps: int = 100
    weight_decay: float = 0.01
    
    # Evaluation
    eval_steps: int = 100
    save_steps: int = 100
    save_total_limit: int = 3
    
    # DPO specific
    beta: float = 0.1
    loss_type: str = "sigmoid"
)
```

## Features

### 1. Dataset Preparation

**InstructionDataset** - Format instruction-following data:
```python
preparator = DatasetPreparator("model-name")
train, eval = preparator.prepare_instruction_dataset(
    samples,
    max_length=512,
    train_ratio=0.8
)
```

**DPODataset** - Prepare preference pair data:
```python
train, eval = preparator.prepare_dpo_dataset(
    samples,
    max_length=512,
    train_ratio=0.8
)
```

### 2. LoRA Instruction Tuning

Train with parameter-efficient adapters:
```python
tuner = LoRAInstructionTuner(lora_config, training_args)
result = tuner.train(train_dataset, eval_dataset)
tuner.save("./outputs/model")
```

### 3. DPO Alignment

Optimize for human preferences:
```python
dpo_trainer = DPOTrainer("model-name", training_args, lora_config)
dpo_trainer.train(train_dataset, eval_dataset)
dpo_trainer.save("./outputs/dpo_model")
```

### 4. Catastrophic Forgetting Prevention

Multiple strategies built-in:

**Embedding Distance Monitoring**
```python
detector = CatastrophicForgettingDetector("model-name")
distance = detector.compute_embedding_distance(model, golden_set)
is_forgetting, _ = detector.detect_forgetting(model, golden_set, threshold=0.7)
```

**Fisher Information Matrix (Elastic Weight Consolidation)**
```python
fisher = detector.compute_fisher_information(model, golden_set)
ewc_loss = detector.compute_ewc_loss(model, fisher, reference_params, lambda_ewc=0.4)
```

**Perplexity Tracking**
```python
evaluator = ModelEvaluator("model-name")
ppl = evaluator.compute_perplexity(model, golden_set_dataset)
```

### 5. Model Evaluation

**Before/After Comparison**
```python
evaluator = ModelEvaluator("model-name")
comparison = evaluator.compare_models(
    base_model_path=None,  # Uses base model
    finetuned_model_path="./lora_adapters",
    benchmark_samples=benchmark_data
)
```

**Benchmark Evaluation**
```python
results = evaluator.evaluate_on_benchmark(model, benchmark_samples)
print(results["exact_match_rate"])
print(results["partial_match_rate"])
```

## Usage Examples

### Command Line

**Instruction Tuning**
```bash
python -m src.ragstack.finetuning.cli instruction-tuning \
  --model meta-llama/Llama-2-7b-hf \
  --data instructions.jsonl \
  --epochs 3 \
  --batch-size 4 \
  --lora-r 8
```

**DPO Alignment**
```bash
python -m src.ragstack.finetuning.cli dpo-alignment \
  --model meta-llama/Llama-2-7b-hf \
  --data dpo.jsonl \
  --epochs 1 \
  --beta 0.1
```

**Evaluate Forgetting**
```bash
python -m src.ragstack.finetuning.cli detect-forgetting \
  --model meta-llama/Llama-2-7b-hf \
  --adapter ./lora_adapters \
  --golden-set golden.jsonl
```

### Python API

**Full Pipeline**
```python
from src.ragstack.finetuning import FineTuningPipeline

pipeline = FineTuningPipeline("meta-llama/Llama-2-7b-hf")

# Step 1: Instruction tuning
result1 = pipeline.run_instruction_tuning(
    "instructions.jsonl",
    benchmark_data_path="benchmark.jsonl"
)

# Step 2: DPO alignment
result2 = pipeline.run_dpo_alignment("dpo.jsonl")

# Step 3: Check for forgetting
result3 = pipeline.evaluate_catastrophic_forgetting(
    "adapter_path",
    "golden_set.jsonl"
)

# Step 4: Before/after comparison
result4 = pipeline.run_before_after_evaluation(
    "benchmark.jsonl",
    "final_adapter_path"
)
```

## Data Format

### Instructions (JSONL)
```json
{
  "instruction": "Task description",
  "input": "Optional input context",
  "output": "Expected output",
  "system_prompt": "System message for model"
}
```

### DPO Pairs (JSONL)
```json
{
  "prompt": "The query or prompt",
  "chosen": "Preferred response",
  "rejected": "Dispreferred response"
}
```

### Benchmark (JSONL)
```json
{
  "prompt": "Test query",
  "expected_output": "Ideal response",
  "keywords": ["key", "terms"]
}
```

## Configuration

### LoRA Parameters

Start with these defaults:
```python
config = FineTuningConfig(
    model_name="meta-llama/Llama-2-7b-hf",
    lora_r=8,              # Rank 8-16 for 7B models
    lora_alpha=16,         # Usually 2x rank
    lora_dropout=0.05,     # 5% dropout
    target_modules=["q_proj", "v_proj"]  # Query & value projections
)
```

### Training Parameters

Tuned for efficiency:
```python
args = TrainingArgs(
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,  # Effective batch=16
    learning_rate=2e-4,
    warmup_steps=100,
    num_train_epochs=3,
    bf16=True,  # bfloat16 for speed
    eval_steps=100,
    save_steps=100
)
```

## Performance

### Memory Usage

- **Base model (7B)**: ~16GB VRAM
- **With LoRA (rank 8)**: ~18GB VRAM (10% overhead)
- **Trainable params**: 0.1-0.5% of total

### Training Speed

- **Single GPU (A100)**: ~100-150 samples/sec
- **Batch size 4, seq_len 512**: ~20-30 mins per epoch
- **Full pipeline**: 1-3 hours on single GPU

## Troubleshooting

### Out of Memory

```python
# Reduce batch size
args.per_device_train_batch_size = 2

# Increase gradient accumulation
args.gradient_accumulation_steps = 8

# Use 8-bit quantization
model = AutoModelForCausalLM.from_pretrained(model_id, load_in_8bit=True)
```

### Catastrophic Forgetting

```python
# Larger golden set
golden_set = preparator.create_golden_set(data, ratio=0.1)

# Lower learning rate
args.learning_rate = 1e-4

# More warmup steps
args.warmup_steps = 500
```

### Model Overfitting

```python
# Add early stopping
args.eval_steps = 50
args.save_steps = 50

# Increase dropout
config.lora_dropout = 0.1

# Reduce epochs
args.num_train_epochs = 2
```

## Testing

Run the test suite:

```bash
pytest tests/test_finetuning.py -v
```

Run integration tests (requires CUDA):

```bash
pytest tests/test_finetuning.py -v -m integration
```

## References

- [LoRA Paper](https://arxiv.org/abs/2106.09685)
- [DPO Paper](https://arxiv.org/abs/2305.18290)
- [Elastic Weight Consolidation](https://arxiv.org/abs/1612.00796)
- [PEFT Documentation](https://huggingface.co/docs/peft/)
- [Transformers Documentation](https://huggingface.co/docs/transformers/)

## API Reference

### FineTuningPipeline

```python
class FineTuningPipeline:
    def __init__(model_name, output_dir, lora_config, training_args)
    def run_instruction_tuning(data_path, benchmark_path, use_golden_set) -> Dict
    def run_dpo_alignment(data_path, pretrained_adapter_path) -> Dict
    def evaluate_catastrophic_forgetting(adapter_path, golden_set_path, threshold) -> Dict
    def run_before_after_evaluation(benchmark_path, adapter_path) -> Dict
    def save_config()
    def load_checkpoint(checkpoint_path)
```

### DatasetPreparator

```python
class DatasetPreparator:
    def load_jsonl(path) -> List[Dict]
    def validate_instruction_format(samples) -> bool
    def validate_dpo_format(samples) -> bool
    def split_dataset(samples, train_ratio) -> Tuple
    def prepare_instruction_dataset(samples, max_length, train_ratio) -> Tuple
    def prepare_dpo_dataset(samples, max_length, train_ratio) -> Tuple
    def create_golden_set(samples, ratio) -> List[Dict]
```

### ModelEvaluator

```python
class ModelEvaluator:
    def load_model(model_path) -> Model
    def generate_text(model, prompt, max_length, temperature) -> str
    def compute_perplexity(model, dataset, batch_size) -> float
    def evaluate_on_benchmark(model, samples) -> Dict
    def compare_models(base_path, finetuned_path, samples) -> Dict
```

### CatastrophicForgettingDetector

```python
class CatastrophicForgettingDetector:
    def compute_embedding_distance(model, golden_set) -> float
    def detect_forgetting(model, golden_set, threshold) -> Tuple[bool, float]
    def compute_fisher_information(model, golden_set, batch_size) -> Dict
    def compute_ewc_loss(model, fisher, reference_params, lambda_ewc) -> Tensor
```

## License

Same as parent project.

## Contributing

Contributions welcome! Please ensure:
1. Tests pass (`pytest tests/test_finetuning.py`)
2. Code formatted with black/isort
3. Type hints included
4. Docstrings for public methods
