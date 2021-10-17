#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import sys
import read_digest_list


def main():
    drop_size = 0
    drop_count = 0
    total_size = 0
    total_count = 0
    known_data = (dict(), dict())
    for f in sys.argv[1:-1]:
        known_data = read_digest_list.read(f, known_data)
    new_data = read_digest_list.read(sys.argv[-1])

    files_to_drop = list()
    for i in new_data[1]:
        filename = new_data[1][i][0]
        if i in known_data[1]:
            drop_size += new_data[0][filename][1]
            drop_count += 1
            size = read_digest_list.format_size(new_data[0][filename][1])
            files_to_drop.append((filename, size))
        total_size += new_data[0][filename][1]
        total_count += 1

    for filename, size in files_to_drop:
        print(size.rjust(8), filename)

    print("\n\n")
    print(f"Found: {drop_count} files to delete ({read_digest_list.format_size(drop_size)})")
    print(f"On a total of {total_count} files ({read_digest_list.format_size(total_size)})")
    return 0


if __name__ == "__main__":
    exit(main())
