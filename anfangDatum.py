import json

def process_row(row):
    user_id, name, amount = row.strip().split(",")

    return {
        "user_id": int(user_id),
        "name": name.upper(),
        "amount": float(amount)
    }

with open("sample.csv", "r") as infile, \
     open("output.jsonl", "w") as outfile:

    next(infile)

    for line in infile:
        transformed = process_row(line)

        outfile.write(json.dumps(transformed) + "\n")