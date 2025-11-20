import random, string

def send_otp_console(email):
    otp = ''.join(random.choice(string.digits) for _ in range(6))
    print(f"[OTP for {email}] -> {otp}")
    return otp

def generate_virtual_card_number():
    return " ".join(["".join(random.choice(string.digits) for _ in range(4)) for _ in range(4)])

def detect_fraud(amount, account):
    if amount > 100000:  # threshold demo
        return True
    return False
