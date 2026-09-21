"""RPG Stage 1 peptide-library generation.

The partitioning and output order intentionally match the implementation in
the published RPG project. Keeping this code independent from Qt makes the
scientific result straightforward to verify.
"""

from concurrent.futures import ThreadPoolExecutor
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping, Sequence


PeptideOptions = Mapping[int, Sequence[str]]


def generate_peptide_library(peptide_options: PeptideOptions, destination: Path) -> int:
    """Write the RPG peptide library and return the number of sequences."""
    length = len(peptide_options)
    if length == 0:
        raise ValueError("At least one peptide position is required")

    amino_acid_lists = [tuple(peptide_options[index]) for index in range(length)]
    if any(not choices for choices in amino_acid_lists):
        raise ValueError("Every peptide position needs at least one amino acid")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix=".rpg-stage1-", dir=destination.parent) as temp_name:
        temp_dir = Path(temp_name)
        with ThreadPoolExecutor(max_workers=length) as executor:
            futures = [
                executor.submit(
                    _write_partition,
                    amino_acid_lists,
                    length,
                    process_index,
                    temp_dir / str(process_index),
                )
                for process_index in range(length)
            ]
            counts = [future.result() for future in futures]

        with destination.open("w", encoding="utf-8", newline="\n") as output_file:
            for process_index in range(length):
                output_file.write((temp_dir / str(process_index)).read_text(encoding="utf-8"))

    return sum(counts)


def _write_partition(
    amino_acid_lists: Sequence[Sequence[str]],
    length: int,
    process_index: int,
    destination: Path,
) -> int:
    count = 0
    buffer = []

    with destination.open("w", encoding="utf-8", newline="\n") as output_file:
        for combination in product(*amino_acid_lists):
            index_sum = sum(
                amino_acid_lists[index].index(amino_acid)
                for index, amino_acid in enumerate(combination)
            )
            if index_sum % length != process_index:
                continue

            buffer.append("".join(combination) + "\n")
            count += 1
            if len(buffer) == 1_000_000:
                output_file.writelines(buffer)
                buffer.clear()

        output_file.writelines(buffer)

    return count
