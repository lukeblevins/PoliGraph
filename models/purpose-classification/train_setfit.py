#!/usr/bin/env python3
"""Train the SetFit model for purpose classification"""

import argparse
import json

import numpy as np
import pandas as pd
from datasets import Dataset
from setfit import SetFitModel, Trainer, TrainingArguments
from sklearn.metrics import precision_recall_fscore_support

PURPOSE_LABELS = [
    "advertising",
    "analytics",
    "legal",
    "security",
    "services",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("train_dataset", help="Training set")
    parser.add_argument("test_dataset", help="Testing set")
    parser.add_argument("output", help="Output model path")
    parser.add_argument("--metrics-output", help="Write held-out metrics as JSON")
    args = parser.parse_args()

    train_dataset = Dataset.from_json(args.train_dataset, keep_in_memory=True)
    test_dataset = Dataset.from_json(args.test_dataset, keep_in_memory=True)


    # Load SetFit model from Hub
    model = SetFitModel.from_pretrained(
        "sentence-transformers/paraphrase-mpnet-base-v2",
        multi_target_strategy="one-vs-rest"
    )

    training_args = TrainingArguments(
        output_dir=f"{args.output}-checkpoints",
        batch_size=16,
        num_iterations=20,
        num_epochs=2,
        use_amp=True,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=test_dataset,
    )

    # Train and evaluate!
    trainer.train()
    predictions = model(test_dataset["text"])
    y_pred = predictions.cpu().numpy() if hasattr(predictions, "cpu") else np.asarray(predictions)
    y_true = np.array(test_dataset["label"])
    precisions, recalls, fscores, supports = precision_recall_fscore_support(y_true, y_pred)

    statistic = pd.DataFrame.from_dict({
        "label": PURPOSE_LABELS,
        "precision": precisions,
        "recall": recalls,
        "fscore": fscores,
        "support": supports,
    })
    print(statistic)
    metrics = {
        "labels": statistic.to_dict(orient="records"),
        "macro_precision": float(np.mean(precisions)),
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(np.mean(fscores)),
    }
    print(json.dumps(metrics, indent=2))
    if args.metrics_output:
        with open(args.metrics_output, "w", encoding="utf-8") as fout:
            json.dump(metrics, fout, indent=2)

    model.save_pretrained(args.output, safe_serialization=True)


if __name__ == "__main__":
    main()
