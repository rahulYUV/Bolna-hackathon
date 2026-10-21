"""One working Sarvam AI call: a plain chat completion, then the extraction
path against a sample Hindi/Hinglish Bolna transcript.

Run with the project venv:
    venv\\Scripts\\python sarvam_test.py
"""

from app.sarvam import MODEL, extract_outcome, get_client

SAMPLE_TRANSCRIPT = """\
assistant: Namaste Ramesh ji, main Sharma General Store ki taraf se bol rahi hoon.
Aapke yahan 500 rupaye ka udhaar baaki hai. Kab de payenge?
user: Haan haan, Friday ko de dunga, pakka.
assistant: Theek hai, Ramesh ji, humne note kar liya hai. Dhanyavaad.
"""


def main() -> None:
    client = get_client()

    print("=== 1. Plain chat completion ===")
    response = client.chat.completions(
        model=MODEL,
        messages=[{"role": "user", "content": "What is the capital of India?"}],
    )
    print(response.choices[0].message.content)

    print("\n=== 2. Outcome extraction from a Hinglish transcript ===")
    result = extract_outcome(SAMPLE_TRANSCRIPT, amount_due=500)
    print(f"outcome       : {result.outcome.value}")
    print(f"promise_date  : {result.promise_date}")
    print(f"notes         : {result.notes}")
    print(f"claimed_amount: {result.claimed_amount}")
    print(f"raw           : {result.raw}")


if __name__ == "__main__":
    main()
