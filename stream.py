with open("large.csv", "r") as file:
    for line in file:
        process(line)
        