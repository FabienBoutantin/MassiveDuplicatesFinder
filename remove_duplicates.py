#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import os
import json
import shutil
import PythonColorConsole.color_console as color_console
from read_digest_list import get_score
from read_digest_list import format_size


cached_answer = None


def ask_what2do(msg):
    global cached_answer
    if cached_answer is not None:
        return cached_answer
    tail = "[Y]es / [N]o / yes to [A]ll / n[O] to all / a[B]ort >"
    res = None
    idx = 0
    while res not in ("y", "n", "a", "o", "b"):
        if idx % 5 == 0:
            print(msg)
        print(tail, end="")
        try:
            res = input().lower()
        except KeyboardInterrupt as e:
            raise e
        idx += 1
    if res == "y":
        return True
    if res == "n":
        return False
    if res == "a":
        cached_answer = True
        return True
    if res == "o":
        cached_answer = False
        return False
    if res == "b":
        exit("Cancel by user")


def main(cc, batch, input_file, min_size=1024 * 1024, rebase=(None, None)):
    """
    Remove all duplicates pointed by input file
    """
    fd = open(input_file, "rt")
    duplicates = json.load(fd)
    fd.close()
    print(len(duplicates))
    total_size = 0
    for size, dup_lst in duplicates:
        try:
            if size < min_size:
                print("min size reached, other files are left untouched.")
                break
            size_str = format_size(size)
            print(size_str, "", end="")
            dup_lst = [(get_score(item), item) for item in dup_lst]
            to_remove = list()
            handle = True
            for i, (rank, item) in enumerate(sorted(dup_lst, reverse=True)):
                if item.startswith(rebase[0]):
                    item = rebase[1] + item[len(rebase[0]):]
                exists = os.path.exists(item)

                if i != 0:
                    to_remove.append(item)
                    print(" " * (len(size_str) + 1), end="")
                    if exists:
                        cc.yellow()
                    else:
                        cc.red()
                    print(item, end="")
                    cc.reset()
                    print(" (score:", rank, ")")
                else:
                    cc.bold()
                    if not exists:
                        cc.red()
                    print(item, end="")
                    cc.reset()
                    print(" (score:", rank, ")")

                if not exists:
                    handle = False
                    print()

            if not handle:
                print("Not able to do it as files/directory are already removed.")
                print("Try with an up to date duplicate list.")
                continue
            if not ask_what2do("Delete duplicates?"):
                continue
            total_size += size
            if os.path.isdir(to_remove[0]):
                for item in to_remove:
                    print("Removing directory:", item)
                    shutil.rmtree(item)
            else:
                for item in to_remove:
                    print("Removing file:", item)
                    os.remove(item)
        except Exception as e:
            print(e)
    print(format_size(total_size), "saved")
    return


if __name__ == "__main__":
    cc = color_console.ColorConsole()
    batch = False
    input_file = "duplicates.json"
    rebase = ("/media/nas1/", "/share/")
    min_size = 50 * 1024 * 1024  # 50MB
    exit(main(cc, batch, input_file, min_size, rebase))
