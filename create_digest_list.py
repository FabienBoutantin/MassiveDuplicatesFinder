#!/usr/bin/env python3
# -*- coding:utf-8 -*-


import os
import sys
import time
from os.path import join, getsize
import argparse
import hashlib

from multiprocessing import Process, Value, Queue, Lock, cpu_count
import multiprocessing
from ctypes import c_wchar_p

import traceback

import PythonColorConsole.color_console as color_console


# TODO: Add support for non TTY outputs (ie Jenkins)
is_output_atty = sys.stdout.isatty()


def get_exception_string():
    exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
    string = ""
    for item in traceback.format_exception(exceptionType, exceptionValue, exceptionTraceback):
        string += item
    return string


###############################
Kilo = 1024
Mega = Kilo * 1024
Giga = Mega * 1024
Tera = Giga * 1024


def format_size(size):
    if size > Tera:
        return f"{size / Tera:.2f}TB"
    if size > Giga:
        return f"{size / Giga:.2f}GB"
    if size > Mega:
        return f"{size / Mega:.2f}MB"
    if size > Kilo:
        return f"{size / Kilo:.2f}KB"
    return str(size) + "B"


def format_speed(recovery_size, recovery_time):
    return format_size(recovery_size / recovery_time) + "/s"


def format_ETA(remaining_time):
    minute = 60
    hour = 60 * minute
    day = 24 * hour
    days = int(remaining_time / day)
    remaining_time -= day * days
    hours = int(remaining_time / hour)
    remaining_time -= hour * hours
    mins = int(remaining_time / minute)
    remaining_time -= minute * mins
    if days:
        return "%dd%02dh" % (days, hours)
    if hours:
        return "%dh%02dm" % (hours, mins)
    if mins:
        return "%dm%02ds" % (mins, int(remaining_time))
    return "%ds" % (int(remaining_time))


if 0:
    for i in range(17):
        remaining_time = i**2**2 * 15
        print(remaining_time, "sec =>\t", end="")
        print(format_ETA(remaining_time))
    exit(0)

###############################

compute_sum_funct_list = list()


if os.name == "posix":
    # Makes a x2 performance change.
    import subprocess

    def compute_sha_subprocess(filename, multiplier):
        output = subprocess.Popen([control_type + "sum", filename], stdout=subprocess.PIPE).communicate()[0]
        return output.split(b" ")[0]
    compute_sum_funct_list.append((False, compute_sha_subprocess))


multiplier = 1


def compute_sha_python(filename, multiplier):
    m = hashlib.new(control_type)
    size = multiplier * m.block_size
    file = open(filename, "rb")
    buff = file.read(size)
    while len(buff) == size:
        m.update(buff)
        buff = file.read(size)
    m.update(buff)
    file.close()
    return m.hexdigest()


compute_sum_funct_list.append((True, compute_sha_python))


def get_best_sha_function(path):
    if 0:
        return 512, compute_sha_python
    test_file = None
    fallback_testfile = None
    print("\nComputing best policy to process files.", end="")
    sys.stdout.flush()
    try:
        for root, dirs, files in os.walk(path):
            for name in files:
                size = getsize(join(root, name))
                if size == 0:
                    continue
                fallback_testfile = join(root, name)
                if size > Kilo and size < 10 * Kilo:
                    test_file = join(root, name)
                    calls_count = int(20.0 * Kilo / size)  # emulate reading 20Mo
                    break
            if test_file is not None:
                break
    except Exception:
        pass
    if test_file is None:
        if fallback_testfile is None:
            return 1, compute_sum_funct_list[0][1]
        test_file = fallback_testfile
        calls_count = int(20.0)  # reading 20 time the file
    if verbose:
        print(test_file, format_size(getsize(test_file)))

    min_time = 100000
    min_mult = 1
    min_func = compute_sum_funct_list[0][1]
    for use_multiplier, function in compute_sum_funct_list:
        if not use_multiplier:
            start_time = time.time()
            for i in range(calls_count):
                function(test_file, 1)
            run_time = time.time() - start_time
            if run_time < min_time:
                min_time = run_time
                min_mult = 1
                min_func = function
        else:
            mint = 100000
            mini = 1
            for i in range(6, 11):
                mult = 2**i
                start_time = time.time()
                for dummy in range(calls_count):
                    function(test_file, mult)
                run_time = time.time() - start_time
                if verbose:
                    print(mult, run_time)
                if run_time < mint:
                    mint = run_time
                    mini = mult

            for j in range(8):
                mult = mini + (j - 5) * 16
                if mult < 1:
                    continue
                start_time = time.time()
                for dummy in range(calls_count):
                    function(test_file, mult)
                run_time = time.time() - start_time
                if verbose:
                    print(mult, run_time)
                if run_time < mint:
                    mint = run_time
                    mini = mult

            if mint < min_time:
                min_time = mint
                min_mult = mini
                min_func = function
    print("Done\n")
    return min_mult, min_func


###############################

def count_entries(path, file_count, whole_size, q):
    # determine how many files and which size must be treaded
    for root, dirs, files in os.walk(path):
        tmp_cnt = len(files)
        size = 0
        for name in sorted(files):
            filename = join(root, name)
            if not os.path.exists(filename):
                continue
            if os.path.islink(filename):
                tmp_cnt -= 1
                continue
            s = getsize(filename)
            size += s
            q.put((filename, s))
        file_count.value += tmp_cnt
        whole_size.value += size

        if 'CVS' in dirs:
            dirs.remove('CVS')  # don't visit CVS directories
        if '.svn' in dirs:
            dirs.remove('.svn')  # don't visit SVN directories
        dirs_to_remove = list()
        for directory in dirs:
            if os.path.islink(join(root, directory)):
                dirs_to_remove.append(directory)
        for directory in dirs_to_remove:
            dirs.remove(directory)
        dirs.sort()


def my_walk_sp(dir, outfile, autodetect=False):
    dir = os.path.realpath(dir)
    dir_size = len(dir) + 1

    if autodetect:
        multiplier, compute_sha = get_best_sha_function(dir)
    else:
        multiplier, compute_sha = 512, compute_sum_funct_list[-1][1]

    file_count = Value('d', 0.0)
    whole_size = Value('d', 0.0)

    q = Queue()

    p = Process(target=count_entries, args=(dir, file_count, whole_size, q))
    p.start()

    # actually do the job
    done_size = 0
    start_time = time.time()
    computation_time = 0
    computation_size = 0
    w, h = cc.get_size()
    print("Remaining files and size; average speed; ETA; current file size; current file")
    file_id = 0
    res = ""
    while p.is_alive() or not q.empty():
        time.sleep(0)
        try:
            filename, filesize = q.get(False, 10)
        except Exception:
            continue
        filesize_str = format_size(filesize)
        file_mtime = int(os.stat(filename).st_mtime)
        file_id += 1

        if filesize > 5024024 or file_id % 30 == 0:
            enlapsed_time = time.time() - start_time
            remaining_size = whole_size.value - done_size
            remaining_size_str = format_size(remaining_size)

            if verbose:
                output = ""
            else:
                output = "\r"

            output += "%d " % (file_count.value - file_id)
            output += " " * (9 - len(remaining_size_str)) + remaining_size_str

            if computation_size == 0 or computation_time == 0:
                speed = "???MB/s"
                eta = format_ETA(enlapsed_time / file_id * (file_count.value - file_id))
            else:
                speed = format_speed(computation_size, computation_time)
                eta = format_ETA(computation_time / computation_size * remaining_size)
            output += " %s" % speed
            output += " ETA:%s" % eta

            output += " " * (9 - len(filesize_str)) + filesize_str + " "
            if file_id % 100 == 0:
                w, h = cc.get_size()
            small_filename = filename[-1 * (w - len(output)):]
            output += small_filename
            output += " " * (w - len(output))

            print(output.encode("utf8", "replace").decode(), end="")
            sys.stdout.flush()

        clean_filename = filename.encode("utf8", "replace").decode()
        res += ">%s\n" % clean_filename[dir_size:]
        res += "(%s) %s (%i)\n" % (filesize_str, time.ctime(file_mtime), file_mtime)

        if clean_filename in reloaded_entries and reloaded_entries[clean_filename][0] == file_mtime:
            res += "'%s'" % reloaded_entries[clean_filename][1].decode("utf-8")
        else:
            if dry_run:
                res = res + "None"
            else:
                sha_start_time = time.time()
                try:
                    sha_sum = compute_sha(filename, multiplier)
                    computation_time += time.time() - sha_start_time
                    computation_size += filesize
                    res += "'%s'" % sha_sum
                except IOError as e:
                    txt = "\n'%s': %s\n" % (filename, e.strerror)
                    errorfile.write(txt)
                    errorfile.flush()
                    cc.error(txt)
                    continue

        done_size += filesize
        res += "\n\n"
        if filesize > 5024024 or file_id % 50 == 0:
            if verbose:
                print("\n" + res)
            if outfile is not None:
                tmp = open(outfile, "at")
                tmp.write(res)
                tmp.close()
            res = ""
    if len(res) > 0:
        if verbose:
            print("\n" + res)
        if outfile is not None:
            tmp = open(outfile, "at")
            tmp.write(res)
            tmp.close()
    try:
        average_speed = "(%s)" % format_speed(computation_size, computation_time)
    except Exception:
        average_speed = ""
    print(
        "\nHandled %d files" % file_count.value,
        "Computed",
        format_size(computation_size),
        "in",
        format_ETA(computation_time),
        average_speed
    )


def compute_element(dir, multiplier, compute_sha, q, current_file, current_file_size, outfile, p_alive, file_id, computation_size, stdout_lock, files_lock):
    computation_time = 0
    w, h = cc.get_size()
    res = ""
    done = False
    while not done:
        time.sleep(0)
        try:
            filename, filesize = q.get(False, 10)
            current_file.value = filename
            current_file_size.value = filesize
        except Exception:
            if not p_alive.value:
                done = True
            continue

        filesize_str = format_size(filesize)
        try:
            file_mtime = int(os.stat(filename).st_mtime)
        except Exception as e:
            txt = "\n'%s': %s\n" % (filename, e.strerror)
            files_lock.acquire()
            errorfile.write(txt)
            errorfile.flush()
            files_lock.release()
            stdout_lock.acquire()
            cc.error(txt)
            stdout_lock.release()
            continue
        file_id.value += 1

        res += ">%s\n" % filename[len(dir) + 1:].encode("utf8", "replace").decode()
        res += "(%s) %s (%i)\n" % (filesize_str, time.ctime(file_mtime), file_mtime)

        if filename in reloaded_entries and reloaded_entries[filename][0] == file_mtime:
            res += "'%s'" % reloaded_entries[filename][1].decode("utf-8")
        else:
            if dry_run:
                res += "None"
            else:
                sha_start_time = time.time()
                try:
                    sha_sum = compute_sha(filename, multiplier)
                    computation_time += time.time() - sha_start_time
                    computation_size.value += filesize
                    res += "'%s'" % sha_sum
                except IOError as e:
                    txt = "\n'%s': %s\n" % (filename, e.strerror)
                    files_lock.acquire()
                    errorfile.write(txt)
                    errorfile.flush()
                    files_lock.release()
                    stdout_lock.acquire()
                    cc.error(txt)
                    stdout_lock.release()
                    continue

        res += "\n\n"
        if verbose:
            stdout_lock.acquire()
            print("\n" + res)
            stdout_lock.release()
        if file_id.value % 10 == 0:
            if outfile is not None:
                files_lock.acquire()
                tmp = open(outfile, "at")
                tmp.write(res)
                tmp.close()
                files_lock.release()
            res = ""

    if outfile is not None:
        files_lock.acquire()
        tmp = open(outfile, "at")
        tmp.write(res)
        tmp.close()
        files_lock.release()


def my_walk_mp(number_of_process, dir, outfile, autodetect=False):
    dir = os.path.realpath(dir)

    if autodetect:
        multiplier, compute_sha = get_best_sha_function(dir)
    else:
        multiplier, compute_sha = 512, compute_sum_funct_list[-1][1]

    file_count = Value('d', 0.0)
    whole_size = Value('d', 0.0)

    q = Queue()
    current_file = multiprocessing.Manager().Value(c_wchar_p, '???')
    current_file_size = Value('d', 0.0)

    p = Process(target=count_entries, args=(dir, file_count, whole_size, q))
    p.start()

    stdout_lock = Lock()
    files_lock = Lock()
    # actually do the job
    computation_time = 0
    w, h = cc.get_size()
    print("Remaining files and size; average speed; ETA; current file size; current file")

    p_alive = Value('b', True)
    # Start worker processes
    processes = list()
    for i in range(number_of_process):
        file_id = Value('d', 0.0)
        computation_size = Value('d', 0.0)
        processes.append(
            (
                file_id,
                computation_size,
                Process(
                    target=compute_element,
                    args=(
                        dir, multiplier, compute_sha, q, current_file, current_file_size,
                        outfile, p_alive, file_id, computation_size, stdout_lock, files_lock
                    )
                )
            )
        )

    start_time = time.time()
    for file_id, computation_size, process in processes:
        process.start()

    while p.is_alive() or not q.empty():
        if verbose or not is_output_atty:
            output = ""
        else:
            output = "\r"
        remaining_items = file_count.value
        computed_size = 0
        remaining_size = whole_size.value
        for file_id, computation_size, process in processes:
            remaining_items -= file_id.value
            computed_size += computation_size.value
        remaining_size -= computed_size
        remaining_size_str = format_size(remaining_size)

        computation_time = time.time() - start_time

        output += "%d " % remaining_items
        output += " " * (9 - len(remaining_size_str)) + remaining_size_str

        if computation_time == 0 or computed_size == 0:
            speed = "???MB/s"
            eta = "???s"
        else:
            speed = format_speed(computed_size, computation_time)
            eta = format_ETA(computation_time / computed_size * remaining_size)
        output += " %s" % speed
        output += " ETA:%s" % eta

        filesize_str = format_size(current_file_size.value)
        output += " " * (9 - len(filesize_str)) + filesize_str + " "

        if is_output_atty:
            if remaining_items % 100 == 0:
                w, h = cc.get_size()
            small_filename = current_file.value[-1 * (w - len(output)):]
            output += small_filename
            output += " " * (w - len(output))
        else:
            output += current_file.value

        stdout_lock.acquire()
        if verbose or not is_output_atty:
            print(output.encode("utf8", "replace").decode())
        else:
            print(output.encode("utf8", "replace").decode(), end="")
        sys.stdout.flush()
        stdout_lock.release()
        time.sleep(4)

    p_alive.value = p.is_alive()

    for file_id, computation_size, process in processes:
        process.join()

    try:
        average_speed = "(%s)" % format_speed(whole_size.value, computation_time)
    except Exception:
        average_speed = ""
    print("\n\nHandled %d files" % file_count.value, end="")
    print("Computed", format_size(whole_size.value), end="")
    print("in", format_ETA(computation_time), average_speed)


def reload_previous_run(output):
    if not os.path.exists(output):
        return True
    global reloaded_entries
    file = open(output, "rb")
    key = None
    mtime = None
    for line_no, line in enumerate(file, 1):
        # print(line_no)
        if line.startswith(b"# "):
            base = line.strip()[2:]
            key = None
            mtime = None
        elif line.startswith(b">"):
            key = os.path.join(base, line.rstrip()[1:])
            try:
                key = key.decode("utf-8")
            except UnicodeError:
                pass
            mtime = None
        elif key is not None and mtime is None:
            mtime = line.rstrip().split(b" ")[-1][1:-1]
        elif line.startswith(b"'"):
            reloaded_entries[key] = (int(float(mtime)), line.rstrip().strip(b"'\""))
            key = None
            mtime = None
        else:
            key = None
            mtime = None
    file.close()
    return True


control_type = "sha512"
verbose = False
dry_run = False
outfile = None
reloaded_entries = dict()
if __name__ == "__main__":
    cc = color_console.ColorConsole()
    command_line = sys.argv[1:]
    parser = argparse.ArgumentParser()

    parser.set_defaults(mode="sha512")
    parser.add_argument(
        "-f", "--force", dest="force",
        action="store_true", help="Reply 'Yes' to all questions."
    )
    parser.add_argument(
        "-o", "--output", dest="output_name", default="output.txt",
        metavar="FILE", help="write output to FILE"
    )
    parser.add_argument(
        "-a", "--append",
        action="store_true", dest="append", help="Append Digest to FILE content"
    )
    parser.add_argument(
        "-r", "--resume",
        action="append", dest="resume", help="Resume a stopped action"
    )
    parser.add_argument(
        "--md5", action="store_const",
        dest="mode", const="md5", help=""
    )
    parser.add_argument(
        "--sha1", action="store_const",
        dest="mode", const="sha1", help=""
    )
    parser.add_argument(
        "--sha256", action="store_const",
        dest="mode", const="sha256", help=""
    )
    parser.add_argument(
        "--sha512", action="store_const",
        dest="mode", const="sha512", help="Default"
    )
    parser.add_argument(
        '-d', "--autodetect_best_file_access", action="store_true",
        dest="autodetect_best_file_access", help="Try accessing some files with different options to get best access speed."
    )
    parser.add_argument(
        "-p", "--multiprocess", action="store_true",
        dest="multiprocess", help="[Deprecated] Makes computation multi threaded using all CPUs."
    )
    parser.add_argument(
        "-j", nargs="?", default=1, const=cpu_count(), type=int,
        dest="cpu_count", help="Number of concurrent threads."
    )
    # Fix command line to allow `-j` without number
    if "-j" in command_line:
        try:
            int(command_line[command_line.index("-j") + 1])
        except ValueError:
            # if it's not an int, then use maximum CPU available
            command_line.insert(command_line.index("-j") + 1, str(cpu_count()))
    parser.add_argument(
        "-v", "--verbose",
        action="store_true", dest="verbose", help="make lots of noise"
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true", dest="dry_run", help="do no harm"
    )
    parser.add_argument(
        "directories", metavar="DIR", nargs="+", help="Directory to analyze."
    )
    arguments = parser.parse_intermixed_args(command_line)
    if arguments.cpu_count <= 0:
        cc.red()
        print("Error: cannot use negative number of threads.")
        cc.reset()
        parser.print_usage()
        exit(1)
    if arguments.multiprocess:
        cc.yellow()
        print("Warning: -p/--multiprocess option is deprecated, use -j instead.")
        cc.reset()
        arguments.cpu_count = cpu_count()

    control_type = arguments.mode
    if os.path.isfile(arguments.output_name) and not arguments.append:
        cc.warning("Warning, this will overwrite the output file (%s)" % arguments.output_name)
        print()
        if not arguments.force and not cc.acknowledgment("Continue anyway?", True):
            exit(0)
    verbose = arguments.verbose
    dry_run = arguments.dry_run

    cwd = os.getcwd()
    if arguments.resume is not None:
        for item in arguments.resume:
            print("Reading %s file" % item)
            prev_reload_entry_size = len(reloaded_entries)
            if not reload_previous_run(item):
                sys.exit(1)
            print("  => Found", len(reloaded_entries) - prev_reload_entry_size, "entries.")
    # raw_input("Reloaded>")
    for i, arg in enumerate(arguments.directories):
        print("Handling", arg)
        if not os.path.isdir(arg):
            print("  -> is not a directory, do not process.")
            continue
        if not dry_run:
            if arguments.append or i > 0:
                outfile = open(arguments.output_name, "at")
                errorfile = open("errors.log", "at")
            else:
                outfile = open(arguments.output_name, "wt")
                errorfile = open("errors.log", "wt")
            header = "%s\n# %s\n%s\n" % ("#" * 80, os.path.realpath(arg), "#" * 80)
            outfile.write(header)
            outfile.close()
        os.chdir(arg)
        try:
            if outfile is not None:
                if os.path.isabs(arguments.output_name):
                    outfile = arguments.output_name
                else:
                    outfile = os.path.join(cwd, arguments.output_name)
            if arguments.cpu_count > 1:
                print(f"Using {arguments.cpu_count} parallel jobs.")
                my_walk_mp(arguments.cpu_count, ".", outfile, arguments.autodetect_best_file_access)
            else:
                # my_walk_mp(1, ".", outfile, arguments.autodetect_best_file_access)
                my_walk_sp(".", outfile, arguments.autodetect_best_file_access)
        except Exception:
            cc.error("\n\n  %s\n" % get_exception_string())
            sys.exit(-2)
        os.chdir(cwd)
