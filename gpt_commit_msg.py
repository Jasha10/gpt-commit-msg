#!/bin/env python3

from pathlib import Path
import argparse
import logging
import os
import re
import subprocess
import sys
import textwrap

import llmlib

max_token_count = {
    "gpt-4": 8192,
    "gpt-3.5-turbo": 4097
}

def log(path: Path | None, text: str) -> None:
    if path:
        with path.open("a") as f:
            f.write(text + "\n")

def commit_message(llm, diff, prompt, logfile: Path | None = None):
    # Simple case. No summarizing needed.
    tcount = llm.get_num_tokens(prompt + diff)
    logging.info(f"tokens: {tcount}")
    if tcount <= max_token_count[args.model]:
        logging.info(f"Sending prompt + diff:\n{prompt + diff}")
        return llm.ask(prompt + diff)

    logging.warning(f"diff too long. {tcount} tokens. Summarizing...")
    summaries = summarize(llm, diff)
    result = ["## More Detail"] + summaries
    overall_summary = "\n\n".join(summaries)
    while True:
        if llm.get_num_tokens(prompt + overall_summary) <= max_token_count[args.model]:
            break
        # Summarize the summary
        summaries = summarize(llm, overall_summary,
                prompt="Make an unordered list that summarizes the changes described below.n\n")
        result = summaries + ["## More Detail"] + result
        overall_summary = "\n\n".join(summaries)

    result.insert(0, llm.ask(prompt + overall_summary))
    return "\n\n".join(result)

def summarize(llm,
              text,
              splitre=(
                r"^(diff )", # First try to split by diff
                "^$",        # Then try blank line
                "\n",        # Then try newline
                ),
                prompt="Make an unordered list of the effects of every change in this diff.\n\n"
                ):
    query = prompt + text
    tcount = llm.get_num_tokens(query)

    if tcount <= max_token_count[args.model]:
        return [llm.ask(prompt + text)]

    summaries = []
    parts = re.split(splitre[0], text, flags=re.MULTILINE)
    combined_parts = []
    # Now go back through and put the split string back together with the next
    # thing
    for part in parts:
        if re.match(splitre[0], part) or not combined_parts:
            combined_parts.append(part)
        else:
            combined_parts[-1] += part
    parts = combined_parts

    chunk = [parts[0]]
    chunk_tcount = llm.get_num_tokens(parts[0])
    for part in parts[1:]:
        part_tcount = llm.get_num_tokens(part)

        if chunk_tcount + part_tcount >= max_token_count[args.model]:
            text = "".join(chunk)
            chunk = []
            if llm.get_num_tokens(text) > max_token_count[args.model]:
                # Need to split using a different regex
                summaries.extend(summarize(llm, text, splitre=splitre[1:], prompt=prompt))
            else:
                summaries.append(llm.ask(prompt + text))
            chunk_tcount = sum(llm.get_num_tokens(c) for c in chunk)
        chunk.append(part)
        chunk_tcount += part_tcount
    return summaries

args = None
def main():
    parser = argparse.ArgumentParser(
        description="""Use GPT to create source control commit messages.

        Unless other arguments are passed, reads the diff from stdin.
        """)
    parser.add_argument("--git", "-g", help="Use staged git changes.",
                        action="store_true")
    parser.add_argument("--4", "-4", help="Use GPT4 (slower, costs more money)",
                        dest='gpt4', action="store_true")
    def parse_temperature(value: str) -> float:
        temp = float(value)
        if 0 <= temp <= 2:
            return temp
        raise argparse.ArgumentTypeError(f"Temperature must be between 0 and 2, not {value}")
    parser.add_argument("--temperature", "-t", help=("What sampling temperature to use, between 0 and 2."
                                                     " Higher values like 0.8 will make the output more random,"
                                                     " while lower values like 0.2 will make it more focused and deterministic."
                                                     " Default: 0.0 (to give deterministic and precise output)."),
                        action="store", metavar="[0-2]", type=parse_temperature,
                        default=0.0)
    parser.add_argument("--verbose", "-v", help="Print verbose output",
                        action="store_true")
    parser.add_argument("--prompt", "-p", help="Custom prompt to use", action="store",
                        default=re.sub(r"\s+", " ",
                            """Write a git commit message for the following. The message
                            starts with a one-line summary of 60 characters, followed by a
                            blank line, followed by a longer but concise description of the
                            change.""") + "\n\n"
                       )
    parser.add_argument("--quiet", "-q", help="Suppress printing of cache hit counter info",
                        action="store_true")
    parser.add_argument("--logfile", "-l", help="Log file to use",
                        action="store", required=False)
    global args
    args = parser.parse_args()

    if args.git:
        diff = (
            subprocess.check_output(['git', 'diff', '--cached']).decode('utf-8'))
    else:
        diff = sys.stdin.read()
    if len(diff) < 5:
        print("Empty diff.")
        return 1

    if args.gpt4:
        args.model = "gpt-4"
    else:
        args.model = "gpt-3.5-turbo"
    
    if args.quiet:
        quiet = True
    else:
        quiet = False

    if args.logfile:
        logging.basicConfig(filename=os.path.expanduser(args.logfile), level=logging.INFO)

    logging.info(f"Got args: {args}")

    llm = llmlib.Llm(llmlib.Openai(model=args.model, temperature=args.temperature),
                     verbose=args.verbose)

    message = commit_message(llm, diff, args.prompt)
    logging.info(f"GPT returned:\n{message}")
    paragraphs = message.splitlines()
    wrapped_paragraphs = [textwrap.wrap(p) for p in paragraphs]
    wrapped = "\n".join("\n".join(p) for p in wrapped_paragraphs)
    print(wrapped)
    if not quiet:
        print(f"({llm.counter_string()})")

    return 0

if __name__ == "__main__":
    sys.exit(main())
