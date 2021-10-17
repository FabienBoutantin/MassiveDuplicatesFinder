#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import PythonColorConsole.color_console as color_console
import os
import sys
import re
import json


Kilo = 1024
Mega = Kilo * Kilo
Giga = Mega * Kilo
SIZE = {"B": 1, "KB": Kilo, "MB": Mega, "GB": Giga}


def format_size(size):
    if size > Giga:
        return f"{size / Giga:.2f}GB"
    if size > Mega:
        return f"{size / Mega:.2f}MB"
    if size > Kilo:
        return f"{size / Kilo:.2f}KB"
    return str(size) + "B"


def read(filename, data=(dict(), dict())):
    # Do not change it because it's already performant and accurate!
    zero = ord('0')
    nine = ord('9')
    current_data = data[0]
    current_invert = data[1]
    current_entry = ""
    file = open(filename, "rt", encoding="latin1")
    key = None
    mtime = None
    size = None
    value = None
    for line in file:
        if line.startswith(">"):
            key = os.path.join(current_entry, line.rstrip()[1:])
            continue

        if key is not None and mtime is None:
            splitted = line.rstrip().split(" ")
            mtime = splitted[-1][1:-1]
            size = splitted[0][1:-1]
            ordinal = ord(size[-2])
            try:
                if ordinal >= zero and ordinal <= nine:
                    size = int(float(size[:-1]) * SIZE[size[-1]])
                else:
                    size = int(float(size[:-2]) * SIZE[size[-2:]])
            except TypeError:
                size = -1
            continue

        if line.startswith("'"):
            value = line.rstrip()[1:-1]
            current_data[key] = (mtime, size, value)
            if value in current_invert:
                current_invert[value].append(key)
            else:
                current_invert[value] = list()
                current_invert[value].append(key)
            continue

        if line.startswith("# "):
            current_entry = line[1:].strip()
            if current_entry[-1] != "/":
                current_entry += "/"
            continue

        key = None
        mtime = None

    return (current_data, current_invert)


album_art_class = re.compile(r"AlbumArt_\{(.+)\}_(Large|Small)")
good_album_name_class = re.compile(r"\d{4} - .+")


def get_score(entry):
    path, filename = os.path.split(entry)
    filename, ext = os.path.splitext(filename)
    separated_path = path.split(os.path.sep)

    result = 100

    # Path based score
    if "nas1" in separated_path:
        result += 10
    if "£Bcp clef ceed" in separated_path:
        result -= 100
    if "£just_for_playback" in separated_path:
        result -= 100
    if filename.lower().startswith("copy "):
        result -= 90
    if "OldLinux" in separated_path:
        result -= 90
    if "music 60Go" in separated_path:
        result -= 50
    if "musique fred" in separated_path:
        result -= 40
    if "From Thomas" in separated_path:
        result -= 30
    if "Compil à Moi" in separated_path or "My Playlists" in separated_path:
        result -= 10
    if "UnsortedMusique" in separated_path:
        result -= 20
    if "Qusb" in separated_path:
        result -= 20
    if "Sorted_by_artist" in separated_path:
        result -= 1
    if "Disk-35-640Go" in separated_path:
        result += 1

    result -= max(0, 10 - len(separated_path))
    if good_album_name_class.search(separated_path[-1]) is None:
        result -= 15

    # filename based score
    if ext.lower() in (".bmp", ".jpg", ".jpeg", ".db"):
        if album_art_class.search(filename) is not None:
            result -= 5
    if filename.lower() in ("folder", "desktop"):
        result -= 3

    if ext.lower() in (".bak", ".bck"):
        result -= 30

    return max(0, result)


def handle_duplicates(base, duplicates):
    not_actual_diff = True
    must_delete_all = True
    for item in duplicates:
        filename, ext = os.path.splitext(item)
        not_actual_diff = not_actual_diff and ext.lower() in (".ifo", ".bup")
        must_delete_all = must_delete_all and ext.lower() in (".ini", ".txt", ".dat")
    if not_actual_diff:
        return

    sorted_list = list()
    for item in duplicates:
        if item.startswith("./"):
            pretty = os.path.normpath(os.path.join(base, item))
        else:
            pretty = item
        score = get_score(item)
        if score == 100:
            cc.error(f"\nThis path has a perfect score, it's impossible:\n{pretty}")
            sys.exit(-1)
        sorted_list.append((score, pretty))
    sorted_list.sort(reverse=True)

    print()
    cc.bold()
    print(sorted_list[0][1])
    cc.reset()
    for item in sorted_list:
        print(item)

    if must_delete_all:
        cc.warning("Must remove all those files:\n")
        try:
            if not batch:
                if cc.acknowledgment("Delete all those entries"):
                    print("Delete all")
                else:
                    print("Keep them")
        except KeyboardInterrupt:
            sys.exit("\nCancelled by user")

    scores = map(lambda x: x[0], sorted_list)
    if scores[0] == scores[1]:
        cc.error("At least 1st and 2nd have the same score, it's forbiden")
        sys.exit(-1)
    try:
        if not batch:
            if cc.acknowledgment("Only keep the first entry"):
                print("Keep First, and remove other")
            else:
                print("Keep them all")
    except TypeError:
        sys.exit("\nCancelled by user")


def find_duplicated_directories(data):
    use_third_filter = 1  # what?

    folders = dict()
    folder_size = dict()
    for f in data[0]:
        if f is None:
            continue
        split_path = f.split(os.sep)
        for i in range(3, len(split_path)):
            directory = os.sep.join(split_path[:i])
            content = folders.get(directory, list())
            content.append(data[0][f][2])  # just store sum
            folders[directory] = content
            folder_size[directory] = folder_size.get(directory, 0) + data[0][f][1]

    inverted_folders = dict()
    for f in folders:
        key = ",".join(sorted(folders[f]))
        if key in inverted_folders:
            inverted_folders[key].append(f)
            continue
        inverted_folders[key] = [f, ]

    print("First filtering.")
    folders = dict()
    keys = list(inverted_folders.keys())
    for key in keys:
        dup = list()
        for d in inverted_folders[key]:
            add = True
            for dd in dup:
                if d.startswith(dd + os.sep):
                    add = False
                    break
                if dd.startswith(d + os.sep):
                    dup.remove(dd)
                    break
            if add:
                dup.append(d)

        if len(dup) > 1:
            inverted_folders[key] = dup
            for d in dup:
                folders[len(d)] = folders.get(len(d), list()) + [d]
        else:
            del inverted_folders[key]

    print("Second filtering.")
    keys = list(inverted_folders.keys())
    duplicates = list()
    for idx, key in enumerate(keys):
        dup = list()
        print("\r %d/%d" % (idx, len(keys)), end="")
        for d in inverted_folders[key]:
            add = True
            # ld = len(d)
            # for l in folders:
            #     if l >= ld:
            #         continue
            #     for item in folders[l]:
            #         if item == d:
            #             continue
            #         if d.startswith(item+os.sep):
            #             add = False
            #             break
            if add:
                dup.append(d)
        if len(dup) > 1:
            if use_third_filter:
                duplicates.append((folder_size[dup[0]], dup))
            else:
                duplicates.append((folder_size[dup[0]] * (len(dup) - 1), dup))

    if use_third_filter:
        print("\nThird filtering.")
        sorted_dup = sorted(duplicates, reverse=True)
        duplicates = list()
        folders_so_far = list()
        for idx, (size, dup) in enumerate(sorted_dup):
            print("\r %d/%d" % (idx, len(sorted_dup)), len(folders_so_far), end="")
            new_dup = list()
            for d in dup:
                add = True
                for fsf in folders_so_far:
                    if d.startswith(fsf):
                        add = False
                        break
                if add:
                    new_dup.append(d)
            if len(new_dup) > 1:
                duplicates.append((size * (len(new_dup) - 1), new_dup))
                for d in new_dup:
                    folders_so_far.append(d + os.sep)

    print()
    cc.bold()
    print(f"Found {len(duplicates)} duplicate directoy(ies) (not counting original)")
    # print("Duplicates represent " + format_size( size )) + " on " + format_size( total_size ) +" (~%d%%)" % (100*size // total_size)
    cc.reset()
    print()

    return duplicates


def find_duplicated_files(data):
    dup_count = 0
    dup_grp_count = 0
    size = 0.0
    total_size = 0.0
    duplicates = list()
    for key in data[1]:
        cur = data[1][key]
        total_size += data[0][cur[0]][1] * len(cur)
        if len(cur) > 1:
            dup_count += len(cur) - 1
            dup_grp_count += 1
            dup_size = data[0][cur[0]][1] * (len(cur) - 1)
            size += dup_size
            duplicates.append((dup_size, cur))

    print
    cc.bold()
    print(f"Found {dup_count} duplicate file(s) (not counting original) in {dup_grp_count} groups")
    print("Duplicates represent " + format_size(size)) + " on " + format_size(total_size) + " (~%d%%)" % (100 * size // total_size)
    cc.reset()
    print

    return duplicates


def main(cc):
    # TODO: add a way to find duplicated directories!

    data = (dict(), dict())

    cc.magenta()
    for item in sys.argv[1:]:
        print("Reading", item)
        read(item, data)
    cc.reset()

    if 1:
        duplicates = find_duplicated_directories(data)
    else:
        duplicates = find_duplicated_files(data)

    duplicates.sort(reverse=True)

    with open("duplicates.json", "wt") as fd:
        json.dump(duplicates, fd)

    done = False
    page = 0
    page_size = 10
    page_count = (len(duplicates) + page_size - 1) / page_size
    while not done:
        for size, dup_lst in duplicates[page * page_size:(page + 1) * page_size]:
            size = format_size(size)
            cc.bold()
            cc.blue()
            print(size, "", end="")
            cc.reset()
            dup_lst = ((get_score(item), item) for item in dup_lst)
            for i, (rank, item) in enumerate(sorted(dup_lst, reverse=True)):
                if i != 0:
                    print(" " * (len(size) + 1), end="")
                    cc.yellow()
                    print(item, end="")
                    cc.reset()
                    print(" (score:", rank, ")")
                else:
                    cc.bold()
                    print(item, end="")
                    cc.reset()
                    print(" (score:", rank, ")")
        page += 1
        if not batch:
            cc.message("Page %d/%d\n" % (page, page_count))
            if page < page_count:
                done = not cc.acknowledgment("Show another page of duplicates?")
            else:
                done = True
        else:
            done = True
#        if data[0][cur[0]][1] >= 900*Mega:
#            cc.bold()
#            cc.yellow()
#            print "#" * 80
#            cc.reset()
#            for item in sorted(cur):
#                cc.red()
#                print "* ",
#                cc.reset()
#                print item
        # handle_duplicates(cur)


batch = 1

if __name__ == "__main__":
    cc = color_console.ColorConsole()
    main(cc)
