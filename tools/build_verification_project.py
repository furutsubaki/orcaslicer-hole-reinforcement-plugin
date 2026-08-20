"""issue15の統合検証で使う3mfプロジェクトとCLIベースラインを生成する。"""

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "test-models" / "fixtures"
DEFAULT_ORCASLICER = Path(
    "/Applications/OrcaSlicer Nightly.app/Contents/MacOS/OrcaSlicer"
)
DEFAULT_DATADIR = Path.home() / "Library" / "Application Support" / "OrcaSlicer"

MATRIX_PREFIX = "matrix-"
EXPECTED_MATRIX_COUNT = 30
PROJECT_NAME = "verify-matrix.3mf"
MODEL_SETTINGS_ENTRY = "Metadata/model_settings.config"

DEFAULT_MACHINE = "system/Creality/machine/Creality K2 Plus 0.4 nozzle.json"
DEFAULT_PROCESS = (
    "system/Creality/process/0.20mm High Quality @Creality K2 Plus 0.4 nozzle.json"
)
DEFAULT_FILAMENT = "system/Creality/filament/CR-PLA @K2 Plus-all.json"


class ProjectBuildError(RuntimeError):
    pass


def select_matrix_fixtures(entries, *, expected_count=EXPECTED_MATRIX_COUNT):
    """manifestからスライス検証対象のmatrixフィクスチャを選ぶ。

    意図的非多様体のフィクスチャは`printable: false`により除外される。
    """
    selected = {}
    for entry in entries:
        name = entry.get("id") or ""
        if not name.startswith(MATRIX_PREFIX):
            continue
        if not entry.get("printable", False):
            continue
        if name in selected:
            raise ProjectBuildError(f"matrixフィクスチャが重複しています: {name}")
        selected[name] = entry
    if len(selected) != expected_count:
        raise ProjectBuildError(
            "matrixフィクスチャの件数が期待と一致しません: "
            f"期待{expected_count}件、実際{len(selected)}件"
        )
    return [selected[name] for name in sorted(selected)]


def parse_object_names(xml_text):
    root = ET.fromstring(xml_text)
    names = []
    for element in root.findall("object"):
        name = None
        for metadata in element.findall("metadata"):
            if metadata.get("key") == "name":
                name = metadata.get("value")
                break
        if not name:
            raise ProjectBuildError(
                f"3mfのオブジェクトに名前がありません: id={element.get('id')}"
            )
        names.append(name)
    return names


def fixture_name_from_object_name(object_name):
    return object_name[:-4] if object_name.endswith(".stl") else object_name


def build_object_map(object_names, fixture_names):
    mapping = {}
    for object_name in object_names:
        fixture = fixture_name_from_object_name(object_name)
        if fixture in mapping:
            raise ProjectBuildError(
                f"3mf内でオブジェクト名が重複しています: {object_name}"
            )
        mapping[fixture] = object_name
    missing = sorted(set(fixture_names) - set(mapping))
    if missing:
        raise ProjectBuildError(
            "3mfに含まれないフィクスチャがあります: " + ", ".join(missing)
        )
    unexpected = sorted(set(mapping) - set(fixture_names))
    if unexpected:
        raise ProjectBuildError(
            "3mfに想定外のオブジェクトが含まれます: " + ", ".join(unexpected)
        )
    return mapping


def read_project_object_names(project_path):
    with zipfile.ZipFile(project_path) as archive:
        try:
            payload = archive.read(MODEL_SETTINGS_ENTRY)
        except KeyError as error:
            raise ProjectBuildError(
                f"3mfに{MODEL_SETTINGS_ENTRY}がありません: {project_path}"
            ) from error
    return parse_object_names(payload.decode("utf-8"))


def clone_datadir(source, destination):
    """GUI起動中でも競合しないよう、datadirを複製してCLIへ渡す。"""
    if not source.is_dir():
        raise ProjectBuildError(f"datadirが見つかりません: {source}")
    resolved_source = source.resolve()
    resolved_destination = destination.resolve()
    # 複製先を消してから作るため、実datadirと重なっていると本体を削除してしまう。
    if (
        resolved_destination == resolved_source
        or resolved_source in resolved_destination.parents
        or resolved_destination in resolved_source.parents
    ):
        raise ProjectBuildError(
            f"複製先がdatadirと重なっています: {destination}（datadir: {source}）"
        )
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, symlinks=True)
    return destination


def resolve_preset(datadir, value):
    path = Path(value)
    resolved = path if path.is_absolute() else datadir / path
    if not resolved.is_file():
        raise ProjectBuildError(f"プリセットが見つかりません: {resolved}")
    return resolved


def run_orcaslicer(executable, arguments, *, log_path):
    if not executable.is_file():
        raise ProjectBuildError(f"OrcaSlicerが見つかりません: {executable}")
    completed = subprocess.run(
        [str(executable), *arguments, "--logfile", str(log_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed


def _require_output(completed, expected, *, action):
    """CLIは設定不備でも終了コード0を返すことがあるため、成果物の有無で判定する。"""
    if expected.is_file():
        return
    detail = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    raise ProjectBuildError(f"{action}に失敗しました: {detail or '出力なし'}")


def build_project(
    *,
    fixtures_dir,
    work_dir,
    executable,
    datadir,
    machine,
    process,
    filament,
    reuse_datadir=False,
    build_baseline=True,
):
    manifest_path = fixtures_dir / "manifest.json"
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = select_matrix_fixtures(entries)
    fixture_names = [entry["id"] for entry in selected]
    stl_paths = [fixtures_dir / entry["file"] for entry in selected]
    for stl_path in stl_paths:
        if not stl_path.is_file():
            raise ProjectBuildError(f"フィクスチャが見つかりません: {stl_path}")

    work_dir.mkdir(parents=True, exist_ok=True)
    datadir_clone = work_dir / "datadir"
    if reuse_datadir and datadir_clone.is_dir():
        pass
    else:
        clone_datadir(datadir, datadir_clone)

    machine_path = resolve_preset(datadir_clone, machine)
    process_path = resolve_preset(datadir_clone, process)
    filament_path = resolve_preset(datadir_clone, filament)

    project_path = work_dir / PROJECT_NAME
    if project_path.exists():
        project_path.unlink()
    # --export-3mfは--outputdirと連結されるためファイル名だけを渡す。
    completed = run_orcaslicer(
        executable,
        [
            "--datadir",
            str(datadir_clone),
            "--outputdir",
            str(work_dir),
            "--load-settings",
            f"{machine_path};{process_path}",
            "--load-filaments",
            str(filament_path),
            "--arrange",
            "1",
            "--export-3mf",
            PROJECT_NAME,
            *[str(path) for path in stl_paths],
        ],
        log_path=work_dir / "export-3mf.log",
    )
    _require_output(completed, project_path, action="3mfの生成")

    object_names = read_project_object_names(project_path)
    object_map = build_object_map(object_names, fixture_names)

    result = {
        "project": str(project_path),
        "datadir": str(datadir_clone),
        "presets": {
            "machine": str(machine_path),
            "process": str(process_path),
            "filament": str(filament_path),
        },
        "fixtures": fixture_names,
        "objects": object_map,
    }

    if build_baseline:
        baseline_dir = work_dir / "baseline-cli"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        baseline_gcode = baseline_dir / "plate_1.gcode"
        if baseline_gcode.exists():
            baseline_gcode.unlink()
        completed = run_orcaslicer(
            executable,
            [
                "--datadir",
                str(datadir_clone),
                "--outputdir",
                str(baseline_dir),
                "--slice",
                "0",
                str(project_path),
            ],
            log_path=baseline_dir / "slice.log",
        )
        # 傾斜穴を含むモデルはCLIスライスが失敗する。正式なOFF基準はGUI-OFFなので、
        # ここでの失敗は検証全体の失敗にしない。
        if baseline_gcode.is_file():
            result["baseline_gcode"] = str(baseline_gcode)
        else:
            result["baseline_error"] = (
                (completed.stdout or "").strip()
                or (completed.stderr or "").strip()
                or "出力なし"
            )

    (work_dir / "objects.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--orcaslicer", type=Path, default=DEFAULT_ORCASLICER)
    parser.add_argument("--datadir", type=Path, default=DEFAULT_DATADIR)
    parser.add_argument("--machine", default=DEFAULT_MACHINE)
    parser.add_argument("--process", default=DEFAULT_PROCESS)
    parser.add_argument("--filament", default=DEFAULT_FILAMENT)
    parser.add_argument("--reuse-datadir", action="store_true")
    parser.add_argument("--skip-baseline", action="store_true")
    args = parser.parse_args()

    try:
        result = build_project(
            fixtures_dir=args.fixtures,
            work_dir=args.work_dir,
            executable=args.orcaslicer,
            datadir=args.datadir,
            machine=args.machine,
            process=args.process,
            filament=args.filament,
            reuse_datadir=args.reuse_datadir,
            build_baseline=not args.skip_baseline,
        )
    except ProjectBuildError as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1

    print(f"3mf: {result['project']}")
    print(f"オブジェクト数: {len(result['objects'])}")
    if "baseline_gcode" in result:
        print(f"CLIベースライン: {result['baseline_gcode']}")
    elif "baseline_error" in result:
        print(
            f"CLIベースラインは生成できませんでした: {result['baseline_error']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
