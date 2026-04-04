from payments import create_pix_payment

code, mp_id = create_pix_payment(123456789, 2990, "monthly")
print("PIX:", code[:40], "...")
print("ID:", mp_id)
