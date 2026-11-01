import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.nlu.classifier import IntentClassifier
from app.nlu.intents import FALLBACK_INTENT, INTENT_EXAMPLES
from app.tracking.tracker import Tracker

# Examples la illaadha PUTHU sentences (exact match = 1.0 ah poi accuracy kaattum, adhanaala)
TEST_SET = [
    ("Is it going to rain this evening", "weather"),
    ("How is the weather in Mumbai", "weather"),
    ("Will tomorrow be hot", "weather"),
    ("Give me the forecast for Saturday", "weather"),
    ("Start a countdown for 3 minutes", "set_timer"),
    ("Timer for 45 seconds please", "set_timer"),
    ("Set a 20 minute timer for the oven", "set_timer"),
    ("Remind me to pay the electricity bill tomorrow", "set_reminder"),
    ("Set an alarm for 5:30 in the morning", "set_reminder"),
    ("Remind me to water the plants at 8 pm", "set_reminder"),
    ("What is 72 divided by 9", "calculator"),
    ("Calculate 15 plus 28", "calculator"),
    ("What is the square root of 225", "calculator"),
    ("How much is 8 times 7", "calculator"),
    ("Convert 50 miles to kilometers", "unit_conversion"),
    ("How many ounces are in a pound", "unit_conversion"),
    ("Convert 30 celsius to fahrenheit", "unit_conversion"),
    ("How much is 20 euros in rupees", "currency_conversion"),
    ("Convert 500 dollars to pounds", "currency_conversion"),
    ("What is the pound to rupee rate", "currency_conversion"),
    ("Search for the history of the Eiffel Tower", "web_search"),
    ("Look up how photosynthesis works", "web_search"),
    ("Google the best budget smartphones", "web_search"),
    ("Play some Ilaiyaraaja songs", "play_music"),
    ("Pause the song", "play_music"),
    ("Play my favourite playlist on Spotify", "play_music"),
    ("Switch off the kitchen light", "smart_home"),
    ("Turn on the air conditioner", "smart_home"),
    ("Lock the main door", "smart_home"),
    ("What is the time now", "time_date"),
    ("What day is it tomorrow", "time_date"),
    ("Tell me today's date", "time_date"),
    ("Speak slower please", "assistant_settings"),
    ("Make your voice louder", "assistant_settings"),
    ("Lower your volume", "assistant_settings"),
    ("Good afternoon Nova", "greeting"),
    ("Hi how are you doing", "greeting"),
    ("Hello there", "greeting"),
    ("Tell me a fun fact about space", "general_chat"),
    ("Explain how a car engine works", "general_chat"),
    ("What is the capital of Japan", "general_chat"),
    ("Who wrote Hamlet", "general_chat"),
    ("What is my favourite colour", "general_chat"),
    ("I love filter coffee", "general_chat"),
]

THRESHOLDS = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
CHAT_LIKE = {"general_chat", "greeting"}


def predict(best_intent: str, best_score: float, threshold: float) -> str:
    return best_intent if best_score >= threshold else FALLBACK_INTENT


def main():
    classifier = IntentClassifier()
    tracker = Tracker(settings.mlflow_nlu_experiment)

    # Ovvoru sentence ku best intent + score oru dhadavai mattum edukkurom
    rows = []
    for text, expected in TEST_SET:
        _, _, top = classifier.classify(text)
        best_intent, best_score = top[0]
        rows.append((text, expected, best_intent, best_score))

    n_examples = sum(len(v) for v in INTENT_EXAMPLES.values())
    print(f"\nTest sentences: {len(TEST_SET)} | training examples: {n_examples}")
    print("\nthreshold | accuracy | skill_acc | chat_acc | fallback")
    print("----------+----------+-----------+----------+---------")

    best_threshold, best_accuracy = None, -1.0
    for threshold in THRESHOLDS:
        predictions = [predict(best, score, threshold) for _, _, best, score in rows]
        expected_all = [expected for _, expected, _, _ in rows]

        correct = sum(p == e for p, e in zip(predictions, expected_all))
        skill_rows = [(p, e) for p, e in zip(predictions, expected_all) if e not in CHAT_LIKE]
        chat_rows = [(p, e) for p, e in zip(predictions, expected_all) if e == "general_chat"]

        accuracy = correct / len(rows)
        skill_acc = sum(p == e for p, e in skill_rows) / len(skill_rows)
        chat_acc = sum(p == e for p, e in chat_rows) / len(chat_rows)  # skill ku thappa pogama irukkura rate
        fallback_rate = sum(p == FALLBACK_INTENT for p in predictions) / len(rows)

        print(f"   {threshold:.2f}   |  {accuracy:.2f}    |   {skill_acc:.2f}    |  {chat_acc:.2f}    |  {fallback_rate:.2f}")

        tracker.log_run(
            run_name=f"threshold-{threshold:.2f}",
            params={
                "intent_threshold": threshold,
                "embed_model": settings.embed_model,
                "test_size": len(rows),
                "n_examples": n_examples,
            },
            metrics={
                "accuracy": accuracy,
                "skill_accuracy": skill_acc,
                "chat_accuracy": chat_acc,
                "fallback_rate": fallback_rate,
            },
            tags={"type": "nlu-eval"},
        )

        if accuracy > best_accuracy:
            best_threshold, best_accuracy = threshold, accuracy

    print(f"\nBest threshold by accuracy: {best_threshold:.2f} ({best_accuracy:.2f})")
    print(f"Current .env INTENT_THRESHOLD: {settings.intent_threshold}")

    # Current threshold la thappa aana sentences
    print(f"\nMisclassified at threshold {settings.intent_threshold}:")
    wrong = 0
    for text, expected, best, score in rows:
        predicted = predict(best, score, settings.intent_threshold)
        if predicted != expected:
            wrong += 1
            print(f"  [{score:.2f}] {text!r}: expected={expected}, got={predicted}")
    if wrong == 0:
        print("  (Ellaam correct)")

    if tracker.enabled:
        print(f"\nMLflow UI: {settings.mlflow_tracking_uri}  (experiment: {settings.mlflow_nlu_experiment})")


if __name__ == "__main__":
    main()