import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
from torch.utils.data import DataLoader
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Evaluate model performance before and after fine-tuning."""

    def __init__(self, model_name: str, device: str = "cuda"):
        self.device = device
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def load_model(self, model_path: Optional[str] = None):
        """Load base or fine-tuned model."""
        if model_path:
            logger.info(f"Loading model from {model_path}")
            from peft import PeftModel

            model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.bfloat16,
                device_map="auto",
            )
            model = PeftModel.from_pretrained(model, model_path)
        else:
            logger.info(f"Loading base model {self.model_name}")
            model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.bfloat16,
                device_map="auto",
            )

        return model.eval()

    def generate_text(
        self,
        model,
        prompt: str,
        max_length: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Generate text from prompt."""
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_length=max_length,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id,
            )

        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def compute_perplexity(
        self,
        model,
        dataset,
        batch_size: int = 8,
    ) -> float:
        """Compute model perplexity on dataset."""
        dataloader = DataLoader(dataset, batch_size=batch_size)
        total_loss = 0
        total_tokens = 0

        device = next(model.parameters()).device

        with torch.no_grad():
            for batch in tqdm(dataloader, desc="Computing perplexity"):
                batch = {
                    k: v.to(device) if isinstance(v, torch.Tensor) else v
                    for k, v in batch.items()
                }

                outputs = model(
                    input_ids=batch["input_ids"],
                    attention_mask=batch["attention_mask"],
                    labels=batch["labels"],
                )

                loss = outputs.loss
                total_loss += loss.item() * batch["input_ids"].size(0)
                total_tokens += batch["input_ids"].numel()

        perplexity = np.exp(total_loss / total_tokens)
        logger.info(f"Perplexity: {perplexity:.4f}")
        return float(perplexity)

    def evaluate_on_benchmark(
        self,
        model,
        benchmark_samples: List[Dict],
    ) -> Dict[str, float]:
        """Evaluate on custom benchmark."""
        device = next(model.parameters()).device
        results = {
            "exact_match": 0,
            "partial_match": 0,
            "contains_keywords": 0,
            "generated_samples": [],
        }

        for sample in tqdm(benchmark_samples, desc="Evaluating on benchmark"):
            prompt = sample.get("prompt", "")
            expected = sample.get("expected_output", "")
            keywords = sample.get("keywords", [])

            generated = self.generate_text(model, prompt)
            results["generated_samples"].append(
                {
                    "prompt": prompt,
                    "generated": generated,
                    "expected": expected,
                }
            )

            if generated.strip() == expected.strip():
                results["exact_match"] += 1
            elif expected.lower() in generated.lower():
                results["partial_match"] += 1

            if keywords and any(kw.lower() in generated.lower() for kw in keywords):
                results["contains_keywords"] += 1

        total = len(benchmark_samples)
        results["exact_match_rate"] = results["exact_match"] / total
        results["partial_match_rate"] = results["partial_match"] / total
        results["keywords_rate"] = results["contains_keywords"] / total

        logger.info(f"Benchmark results: {results}")
        return results

    def compare_models(
        self,
        base_model_path: Optional[str],
        finetuned_model_path: str,
        benchmark_samples: List[Dict],
    ) -> Dict[str, any]:
        """Compare base and fine-tuned models."""
        logger.info("Comparing models...")

        base_model = self.load_model(base_model_path)
        finetuned_model = self.load_model(finetuned_model_path)

        base_results = self.evaluate_on_benchmark(base_model, benchmark_samples)
        finetuned_results = self.evaluate_on_benchmark(
            finetuned_model, benchmark_samples
        )

        comparison = {
            "base_model": base_results,
            "finetuned_model": finetuned_results,
            "improvement": {
                "exact_match": (
                    finetuned_results["exact_match_rate"]
                    - base_results["exact_match_rate"]
                ),
                "partial_match": (
                    finetuned_results["partial_match_rate"]
                    - base_results["partial_match_rate"]
                ),
                "keywords": (
                    finetuned_results["keywords_rate"] - base_results["keywords_rate"]
                ),
            },
        }

        logger.info(f"Comparison complete:\n{json.dumps(comparison, indent=2)}")
        return comparison


class CatastrophicForgettingDetector:
    """Detect and prevent catastrophic forgetting during fine-tuning."""

    def __init__(
        self,
        model_name: str,
        reference_model_path: Optional[str] = None,
    ):
        self.model_name = model_name
        self.reference_model_path = reference_model_path
        self.reference_embeddings = {}
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def compute_embedding_distance(
        self,
        model,
        golden_set: List[Dict],
    ) -> float:
        """Compute embedding distance from reference model."""
        device = next(model.parameters()).device

        if not self.reference_embeddings:
            self._build_reference_embeddings()

        total_distance = 0
        num_samples = 0

        with torch.no_grad():
            for sample in golden_set:
                text = sample.get("text", "")
                inputs = self.tokenizer(
                    text, return_tensors="pt", truncation=True, max_length=512
                ).to(device)

                outputs = model(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs["attention_mask"],
                    output_hidden_states=True,
                )

                current_embedding = outputs.hidden_states[-1].mean(dim=1)

                ref_key = text[:50]
                if ref_key in self.reference_embeddings:
                    ref_embedding = self.reference_embeddings[ref_key]
                    distance = torch.nn.functional.cosine_similarity(
                        current_embedding, ref_embedding
                    )
                    total_distance += distance.item()
                    num_samples += 1

        avg_distance = total_distance / num_samples if num_samples > 0 else 0
        logger.info(f"Average embedding distance: {avg_distance:.4f}")
        return avg_distance

    def _build_reference_embeddings(self):
        """Build reference embeddings from original model."""
        if not self.reference_model_path:
            logger.warning("No reference model path provided")
            return

        logger.info("Building reference embeddings...")
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        model.eval()

        device = next(model.parameters()).device

        with torch.no_grad():
            for sample in range(min(100, len(self.reference_embeddings))):
                ref_key = f"sample_{sample}"
                inputs = self.tokenizer(
                    ref_key, return_tensors="pt", truncation=True, max_length=512
                ).to(device)

                outputs = model(
                    input_ids=inputs["input_ids"],
                    output_hidden_states=True,
                )

                embedding = outputs.hidden_states[-1].mean(dim=1)
                self.reference_embeddings[ref_key] = embedding

    def detect_forgetting(
        self,
        model,
        golden_set: List[Dict],
        threshold: float = 0.7,
    ) -> Tuple[bool, float]:
        """Detect if catastrophic forgetting occurred."""
        distance = self.compute_embedding_distance(model, golden_set)

        is_forgetting = distance < threshold
        logger.info(
            f"Catastrophic forgetting detection: {'YES' if is_forgetting else 'NO'} (distance: {distance:.4f}, threshold: {threshold})"
        )

        return is_forgetting, distance

    def compute_fisher_information(
        self,
        model,
        golden_set: List[Dict],
        batch_size: int = 8,
    ) -> Dict[str, torch.Tensor]:
        """Compute Fisher Information Matrix for EWC regularization."""
        logger.info("Computing Fisher Information Matrix...")

        device = next(model.parameters()).device
        fisher = {}

        for name, param in model.named_parameters():
            fisher[name] = torch.zeros_like(param.data)

        model.train()
        num_batches = 0

        for i in range(0, len(golden_set), batch_size):
            batch = golden_set[i : i + batch_size]

            texts = [s.get("text", "") for s in batch]
            inputs = self.tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512,
            ).to(device)

            outputs = model(**inputs, labels=inputs["input_ids"])
            loss = outputs.loss

            model.zero_grad()
            loss.backward()

            for name, param in model.named_parameters():
                if param.grad is not None:
                    fisher[name] += param.grad.data.pow(2)

            num_batches += 1

        for name in fisher:
            fisher[name] /= num_batches

        logger.info(f"Fisher Information computed for {len(fisher)} parameters")
        return fisher

    def compute_ewc_loss(
        self,
        model,
        fisher: Dict[str, torch.Tensor],
        reference_params: Dict[str, torch.Tensor],
        lambda_ewc: float = 0.4,
    ) -> torch.Tensor:
        """Compute Elastic Weight Consolidation loss."""
        ewc_loss = 0
        for name, param in model.named_parameters():
            if name in fisher:
                ewc_loss += (
                    fisher[name]
                    * (param - reference_params[name]).pow(2)
                ).sum()

        return lambda_ewc * ewc_loss
