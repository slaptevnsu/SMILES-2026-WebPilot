from webpilot.llm_client import LLMClient


def main() -> None:
    client = LLMClient()

    response = client.complete(
        system_prompt="You are a concise coding assistant.",
        user_prompt="Reply with exactly: LLM client works",
    )

    print(response)


if __name__ == "__main__":
    main()
