import secrets
import string

AGENT_HEALTH_PROMPTS = (
    "Reply with a brief greeting.",
    "In one sentence, describe what you can help with.",
    "Say hello and confirm you are available.",
)


def random_health_key() -> str:
    return "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)
    )


def random_agent_health_prompt() -> str:
    return secrets.choice(AGENT_HEALTH_PROMPTS)
