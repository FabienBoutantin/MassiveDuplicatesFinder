#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import sys
import read_digest_list


def main():
    total_size = 0
    total_count = 0
    known_data = (dict(), dict())
    for f in sys.argv[1:-1]:
        known_data = read_digest_list.read(f, known_data)
    new_data = read_digest_list.read(sys.argv[-1])
    things_to_copy = list()
    for i in new_data[1]:
        if i not in known_data[1]:
            filename = new_data[1][i][0]
            total_size += new_data[0][filename][1]
            total_count += 1
            size = read_digest_list.format_size(new_data[0][filename][1])
            things_to_copy.append((filename, size))

    for filename, size in sorted(things_to_copy):
        print(size.rjust(8), filename)

    print("\n\n")
    print(f"Total: {total_count} files to copy ({read_digest_list.format_size(total_size)})")
    return 0


if __name__ == "__main__":
    exit(main())
