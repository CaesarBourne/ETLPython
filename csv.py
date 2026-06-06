def read_transactions(filename):

    with open(filename, "r") as file:

        for line in file:
            yield line.strip()def read_transactions(filename):

    with open(filename, "r") as file:

