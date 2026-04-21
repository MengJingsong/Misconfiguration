import csv
import sys

# Check if user provided an argument
if len(sys.argv) < 2:
    print("Usage: python generate_kv.py <num_rows>")
    sys.exit(1)

# Convert argument to integer
num_rows = int(sys.argv[1])

filename = f"kv_{num_rows}.csv"

with open(filename, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["key", "value"])
    for i in range(1, num_rows + 1):
        key = f"k{i:09d}"
        value = f"value{i:09d}"
        writer.writerow([key, value])

print(f"CSV generated: {filename}")

