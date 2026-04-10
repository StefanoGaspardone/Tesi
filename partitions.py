import re
import sys

def get_partitions(word):
    partitions = []
    n = len(word)

    for i in range(2**(n - 1)):
        start = 0
        current_partition = []

        for j in range(n - 1):
            if (i >> j) & 1:
                current_partition.append(word[start:j+1])
                start = j + 1
        
        current_partition.append(word[start:])
        partitions.append(current_partition)

    return partitions

def get_words(str):
    word_regex = r'[a-zA-Z0-9_\.\-]+'
    matches = list(re.finditer(word_regex, str))

    results = []
    results_by_word = {}

    for match in matches:
        word = match.group()

        if word not in results_by_word:
            item = {
                "word": word,
                "count": 1,
                "partitions": get_partitions(word)
            }
            results.append(item)
            results_by_word[word] = item
        else:
            results_by_word[word]["count"] += 1

    return results

def print_partitions(partitions):
    for idx, partition in enumerate(partitions):
        print(f"\t{idx}: {partition}")

def main():
    if len(sys.argv) > 1:
        string = " ".join(sys.argv[1:])
    else:
        string = input("Enter a string: ")

    words_partitions = get_words(string)
    for item in words_partitions:
        print(f"\nWord (len = {len(item['word'])}): {item['word']}, Count: {item['count']}, Partitions ({len(item['partitions'])}):")
        print_partitions(item["partitions"])


if __name__ == "__main__":
    main()