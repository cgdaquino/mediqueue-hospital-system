import re


def validate_patient_registration(name, email, password):
    """Normalize patient identity fields while preserving the exact password."""
    if not isinstance(name,str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError('Enter your name (1–120 characters).')
    if not isinstance(email,str) or len(email.strip()) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email.strip()):
        raise ValueError('Enter a valid email address.')
    if not isinstance(password,str) or not password.strip() or not 8 <= len(password) <= 128:
        raise ValueError('Use a password of 8–128 characters with at least one non-space character.')
    return name.strip(),email.strip().lower(),password
