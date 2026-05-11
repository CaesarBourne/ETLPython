import json
from datetime import datetime

def normalize_row(row):
    try:
        user_id, amount, currency, date = row.strip().split(",")

        return {
            "user_id": int(user_id),
            "amount": float(amount),
            "currency": currency.upper(),
            "date": datetime.strptime(date.replace("/", "-"), "%Y-%m-%d").isoformat()
        }

    except Exception as e:
        raise ValueError(f"Bad row: {row}") from e


def process_file(input_file, output_file, dlq_file):
    with open(input_file, "r") as infile, \
         open(output_file, "w") as outfile, \
         open(dlq_file, "w") as dlq:

        next(infile)  # skip header

        for line in infile:
            try:
                transformed = normalize_row(line)
                outfile.write(json.dumps(transformed) + "\n")

            except Exception as e:
                dlq.write(line)


if __name__ == "__main__":
    process_file("sample.csv", "output.jsonl", "dlq.csv")