def transform(row):

    user_id, amount = row.split(",")

    return {
        "user_id": int(user_id),
        "amount": float(amount)
    }