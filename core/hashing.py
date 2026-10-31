def convert_php_hash(php_hash: str) -> str:
    """PHP password_hash() bcrypt value ($2y$...) -> Django 'bcrypt$<hash>' so it verifies as-is.
    Use this in the data-import script: user.password = convert_php_hash(row['password'])."""
    if not php_hash.startswith(("$2y$", "$2a$", "$2b$")):
        raise ValueError("Not a bcrypt hash")
    return "bcrypt$" + php_hash
