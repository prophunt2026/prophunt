import bcrypt


def hash_password(plain: str) -> str:
    """Hash le mot de passe avec bcrypt (cost factor 12)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Vérifie qu'un mot de passe en clair correspond au hash stocké.
    Utilise bcrypt.checkpw — résistant aux timing attacks.
    Ne jamais logger plain.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
