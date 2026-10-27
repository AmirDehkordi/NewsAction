"""NA-08: trained decision models on Kaggle, Laya-Fin and the ModernBERT-large anchor (PREREG §9).

Modules, in pipeline order:
- ``labels``: H-react / H-mag / H-cont labels from the public panel (train, val-A, val-B; purged);
- ``kaggle_export``: the private Kaggle dataset (masked states, train and val-A labels only), its sha256
  manifest and one kernel directory per planned run;
- the notebook ``notebook/newsaction_laya_fin.ipynb`` (an artifact run on Kaggle, never imported);
- ``import_preds``: verified run outputs back to events, the common prediction schema, 3-seed ensembles;
- ``metrics``: val-A daily IC, Newey–West t, block-bootstrap CI, ECE, temperature fits;
- ``plan``: the throughput pilot and the quota plan (``artifacts/NA-08/throughput.json``);
- ``cards``: the controls and the two model cards;
- ``build``: the CLI that runs them one stage per process.

Configuration: ``configs/training.yaml``. Only ``labels`` reads returns, from ``panel_public`` (sessions
≤ the end of val-B). No module here imports ``newsaction.panel.targets`` or ``newsaction.lock``, and no
module computes a statistic on val-B or test rows (``metrics.require_val_a``).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from newsaction.config import SplitName, load_yaml
from newsaction.paths import CONFIGS

PRODUCER: Final = "newsaction.train.build (NA-08)"
CHUNK: Final = "NA-08"
KAGGLE_DIR: Final = "kaggle"
LABELS: Final = f"{KAGGLE_DIR}/labels.parquet"
DATASET_DIR: Final = f"{KAGGLE_DIR}/dataset"
KERNELS_DIR: Final = f"{KAGGLE_DIR}/kernels"
PREDICTIONS_DIR: Final = f"{KAGGLE_DIR}/predictions"
RUNS_DIR: Final = f"{PREDICTIONS_DIR}/runs"
ARTIFACTS_SUBDIR: Final = "NA-08"
NOTEBOOK: Final = Path(__file__).resolve().parent / "notebook" / "newsaction_laya_fin.ipynb"
TRAINING_CONFIG_PATH: Final = CONFIGS / "training.yaml"

Source = Literal["A_W0", "A_W2", "B_W2"]
SOURCES: Final[tuple[Source, ...]] = ("A_W0", "A_W2", "B_W2")
QuestionId = Literal["react", "mag", "cont"]
QUESTION_IDS: Final[tuple[QuestionId, ...]] = ("react", "mag", "cont")
Variant = Literal["full", "no_reaction", "no_context"]
VARIANTS: Final[tuple[Variant, ...]] = ("full", "no_reaction", "no_context")
Init = Literal["laya", "modernbert"]
MODEL_NAMES: Final[dict[str, str]] = {"laya": "laya_fin", "modernbert": "anchor"}
REACTION_BLOCK: Final = "reaction_so_far"
# Dataset files: the split each one holds and whether it may carry labels (PREREG §9.3, CLAUDE.md D16).
EXPORT_FILES: Final[dict[str, tuple[SplitName, bool]]] = {
    "train": ("train", True),
    "val_a": ("val_a", True),
    "val_b": ("val_b", False),
    "test_callA": ("test", False),
}


def source_of(call: str, window: str) -> Source:
    key = f"{call}_{window}"
    if key not in SOURCES:
        raise ValueError(f"no state source for call {call!r} and window {window!r}")
    return key


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LabelsConfig(_Strict):
    splits: tuple[SplitName, ...]
    edges: tuple[float, ...]
    react_horizon: int = Field(ge=0)
    mag_horizon: int = Field(ge=0)
    cont_horizon: int = Field(ge=0)
    cont_min_abs_g: float = Field(gt=0)
    cont_band: float = Field(gt=0)

    @model_validator(mode="after")
    def _edges_increase(self) -> LabelsConfig:
        if list(self.edges) != sorted(set(self.edges)) or self.edges[0] <= 0:
            raise ValueError("label edges must be positive and strictly increasing")
        return self


class ScoreQuestion(_Strict):
    type: Literal["score"]
    instructions: str = Field(min_length=1)
    criteria: tuple[str, ...]


class BatteryRef(_Strict):
    battery: str


class QuestionsConfig(_Strict):
    react: BatteryRef
    cont: BatteryRef
    mag: ScoreQuestion
    by_source: dict[Source, tuple[QuestionId, ...]]

    @model_validator(mode="after")
    def _every_source(self) -> QuestionsConfig:
        if set(self.by_source) != set(SOURCES):
            raise ValueError(f"by_source must name every source {SOURCES}")
        if any("cont" in qs for s, qs in self.by_source.items() if not s.startswith("B")):
            raise ValueError("H-cont needs the reaction: Call B only")
        return self


class ExportConfig(_Strict):
    seed: int
    reaction_dropout: float = Field(ge=0, lt=1)
    context_dropout: float = Field(ge=0, lt=1)
    context_blocks: tuple[str, ...]
    dataset_id: str = Field(pattern=r"^[a-z0-9-]+/[a-z0-9-]{6,50}$")
    dataset_title: str = Field(min_length=6, max_length=50)
    license: str


class InitSpec(_Strict):
    repo: str
    subfolder: str | None = None
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModelConfig(_Strict):
    max_len: int = Field(gt=0)
    head_max_len: int = Field(gt=0)
    laya: InitSpec
    anchor: InitSpec
    head_layers: int = Field(gt=0)
    act_costs: dict[str, float]
    seeds: tuple[int, ...]
    max_epochs: int = Field(gt=0)
    lr_backbone: float = Field(gt=0)
    lr_head: float = Field(gt=0)
    min_lr: float = Field(ge=0)
    warmup_frac: float = Field(ge=0, lt=1)
    weight_decay: float = Field(ge=0)
    grad_clip: float = Field(gt=0)
    micro_batch: int = Field(gt=0)
    grad_accum: int = Field(gt=0)
    grad_checkpointing: bool
    eval_batch: int = Field(gt=0)
    loss: Literal["rlcd", "soft-ce"]
    rl_samples: int = Field(gt=0)
    sigma_start: float = Field(gt=0)
    sigma_end: float = Field(gt=0)
    w_sph: float = Field(ge=0)
    w_rps: float = Field(ge=0)
    amp: Literal["fp16"]
    time_budget_hours: float = Field(gt=0)
    pip: tuple[str, ...]

    def init_spec(self, init: Init) -> InitSpec:
        return self.laya if init == "laya" else self.anchor


class RunSpec(_Strict):
    name: str = Field(pattern=r"^[a-z0-9-]+$")
    mode: Literal["pilot", "train"]
    init: Init | None = None
    inits: tuple[Init, ...] = ()
    seed: int | None = None
    epochs: int | None = Field(default=None, gt=0)
    shuffle_labels: bool = False
    predict: tuple[Literal["val_a", "val_b", "test"], ...] = ("val_a", "val_b", "test")
    # deferred: planned, not run yet (operator decision); the import ensembles the seeds that exist
    deferred: bool = False
    # time_budget_hours: this run's budget when it must be below the model's (e.g. the quota left at the push)
    time_budget_hours: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _shape(self) -> RunSpec:
        if self.mode == "pilot" and (not self.inits or self.init is not None):
            raise ValueError(f"{self.name}: a pilot lists its inits and has no single init")
        if self.mode == "train" and (self.init is None or self.seed is None):
            raise ValueError(f"{self.name}: a training run needs an init and a seed")
        if "val_a" not in self.predict:
            raise ValueError(f"{self.name}: every run predicts val-A (early stopping, temperatures)")
        return self


class PilotLaunch(_Strict):
    name: str = Field(pattern=r"^[a-z0-9-]+$")
    init: Init
    rehearse: bool
    required: bool
    hparams: dict[str, int | float | bool] = Field(default_factory=dict)


class PilotConfig(_Strict):
    train_fraction: float = Field(gt=0, le=1)
    steps: int = Field(gt=0)
    rehearsal: dict[str, int]
    launches: tuple[PilotLaunch, ...]

    @model_validator(mode="after")
    def _launches(self) -> PilotConfig:
        names = [x.name for x in self.launches]
        if len(set(names)) != len(names) or not any(x.required for x in self.launches):
            raise ValueError("pilot launches need unique names and at least one required launch")
        return self


class KaggleConfig(_Strict):
    accelerator: str
    session_hours: float = Field(gt=0)
    weekly_gpu_hours: float = Field(gt=0)
    kernel_prefix: str = Field(pattern=r"^[a-z0-9-]+$")
    pilot: PilotConfig
    runs: tuple[RunSpec, ...]

    @model_validator(mode="after")
    def _unique(self) -> KaggleConfig:
        names = [r.name for r in self.runs]
        if len(set(names)) != len(names):
            raise ValueError("run names must be unique")
        return self

    def run(self, name: str) -> RunSpec:
        for r in self.runs:
            if r.name == name:
                return r
        raise KeyError(f"no planned run {name!r}")


class DerivedConfig(_Strict):
    react_midpoints: tuple[float, ...]
    mag_midpoints: tuple[float, ...]


class EvaluationConfig(_Strict):
    ece_bins: int = Field(gt=0)
    min_names_per_day: int = Field(gt=0)
    nw_lags: int = Field(ge=0)
    bootstrap_block: int = Field(gt=0)
    bootstrap_reps: int = Field(gt=0)
    bootstrap_seed: int


class ControlsConfig(_Strict):
    shuffle_run: str
    shuffle_permutation_seed: int
    shuffle_t_max: float = Field(gt=0)
    repro_runs: tuple[str, str]
    repro_ic_tol: float = Field(gt=0)


class TrainingConfig(_Strict):
    encoding: Literal["E0", "E1", "E2", "E3", "E4"]
    states: dict[Source, str]
    labels: LabelsConfig
    questions: QuestionsConfig
    export: ExportConfig
    model: ModelConfig
    kaggle: KaggleConfig
    derived: DerivedConfig
    evaluation: EvaluationConfig
    controls: ControlsConfig

    @model_validator(mode="after")
    def _consistent(self) -> TrainingConfig:
        if set(self.states) != set(SOURCES):
            raise ValueError(f"states must name every source {SOURCES}")
        if any(f"_{self.encoding}." not in p for p in self.states.values()):
            raise ValueError(f"every state file must be of encoding {self.encoding}")
        n_levels = len(self.labels.edges) + 1
        if len(self.derived.react_midpoints) != 2 * n_levels - 1:
            raise ValueError("react midpoints must match the 9 signed levels")
        if len(self.derived.mag_midpoints) != n_levels or len(self.questions.mag.criteria) != n_levels:
            raise ValueError("H-mag has one level per |z| bin")
        names = {r.name for r in self.kaggle.runs}
        missing = {self.controls.shuffle_run, *self.controls.repro_runs} - names
        if missing:
            raise ValueError(f"controls name unplanned runs {sorted(missing)}")
        return self


@functools.cache
def _load(path: Path, mtime_ns: int) -> TrainingConfig:
    return TrainingConfig.model_validate(load_yaml(path))


def load_training_config(path: Path = TRAINING_CONFIG_PATH) -> TrainingConfig:
    return _load(path, path.stat().st_mtime_ns)


def training_questions(cfg: TrainingConfig | None = None) -> dict[QuestionId, dict[str, Any]]:
    """The three training questions in Laya's input format ``{type, instructions, criteria}``.

    react and cont are the frozen battery's Q1 and Q6 (option order as in ``configs/questions_v1.yaml``);
    mag is the internal H-mag question of ``configs/training.yaml``.
    """
    from newsaction.states.questions import load_battery

    cfg = load_training_config() if cfg is None else cfg
    battery = load_battery()
    q = cfg.questions
    return {
        "react": battery.questions[q.react.battery].request(),
        "mag": {"type": q.mag.type, "instructions": q.mag.instructions, "criteria": list(q.mag.criteria)},
        "cont": battery.questions[q.cont.battery].request(),
    }


def option_keys(question: dict[str, Any]) -> list[str]:
    """Option keys in the order Laya renders them (level indices for a score)."""
    crit = question["criteria"]
    if question["type"] == "score":
        return [str(i) for i in range(len(crit))]
    return [str(k) for k in crit]
