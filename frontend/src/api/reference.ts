/**
 * The shapes of the demo's static lists that GET /api/screens/reference serves (backend/di/services/screens/reference.py,
 * from fixtures/golden/screens/reference.json), so `ref('NAME')` returns a typed value instead of a cast (refactor
 * step C3, W-07a). One entry per list; tuples are written as they are served.
 */
import type { AutoType } from './access';
import type { Route } from './analytics';
import type { Phase, StageDef } from './case';
import type { CatalogItem, Canon, ConnMethod, SrcType } from './integration';
import type { Tool } from './mcp';
import type { RolePolicy } from './types';
import type { ActType, Fixed } from './workflowGraph';
import type { Xf } from './workflows';

type Dict<T> = Record<string, T>;
/** [id, label, description] and similar three-text rows. */
type Row3 = [string, string, string];
/** A journey step: [n, title, kind ("built" …), description]. */
type JourneyRow = [number, string, string, string];

interface ClassDef { label: string; plural: string; pre: string; pnew: number; tau: number; weight: number; mfr: string[] }
interface NavGroup { id: string; label: string; icon: string; sub: string; kids: string[][]; leaf?: boolean; mode?: number; sec?: string }
interface PageDef { t: string; sub: string; icon: string; j: number[] }
interface ModelRow { v: string; released: string; from: number; to: number; k: number; bias: number }
interface LrModel { v: string; kind: 'ML' | 'DL'; algo: string; task: string; data: string }
interface Intent { id: string; title: string; area: string; need: string | null; ctx?: string }
interface Eval { as: string; intent: string | null; q?: string; card?: string | null; ctx?: { id: string; kind: string }; noState?: boolean; result?: string }
interface TableSuggestion { n: string; cl: string; desc: string; cols: string[] }
interface TableModel { cl: [string, string][]; fk: Row3[]; t: { n: string; cl: string; desc: string; rows: string; cols: [string, string][] }[] }

export interface Reference {
  ACT_TYPES: ActType[];
  AF_AUTO_TYPES: AutoType[];
  AF_BADGE_TIP: Dict<string>;
  AF_EVALS: Eval[];
  AF_INTENTS: Intent[];
  AF_LEVELS: Row3[];
  AF_LV_RANK: Dict<number>;
  AF_STAGES: StageDef[];
  AF_STAGE_AGENT: Dict<string>;
  AF_STARTERS: Dict<string[]>;
  AS_OF: string;
  AUTH_OPTS: string[];
  CANON: Canon[];
  CANON_EX: Dict<unknown>;
  CANON_PFX: Dict<string>;
  CAP_LBL: Dict<string>;
  CATALOG: CatalogItem[];
  CC_CAP: Dict<number>;
  CC_DESC: Dict<string>;
  CC_DUE: Row3[];
  CC_EST: Dict<number>;
  CC_LAYOUT: Dict<Dict<unknown>>;
  CC_REASONS: string[];
  CC_STAGES: Row3[];
  CH_ARR: Dict<string>;
  CH_DEL: Dict<string>;
  CH_ING: Dict<string>;
  CLASSES: Dict<ClassDef>;
  CLS_ICON: Dict<string>;
  COMPS: string[];
  CONN_METHODS: Dict<ConnMethod>;
  DELEG: Row3[];
  DELIVER: Dict<string[]>;
  /** per asset class: [label, kind ("pct" …)] */
  DIAG: Dict<[string, string]>;
  EQUIP: { cls: string; m: string }[];
  EX_FX: number;
  /** per method: [label, description] */
  EX_MC: Dict<[string, string]>;
  FACILITIES: string[];
  FEAT: Dict<boolean>;
  FR_AK: [string, string][];
  FR_AUTH: Row3[];
  FR_CATOF: Dict<string>;
  FR_CATS: string[];
  FR_DEC: [string, string, string[]][];
  FR_INT_KIDS: [string, string, string, string?][];
  FR_INT_SUB: Dict<string>;
  FR_MODES: [string, string, string, string][];
  FR_MODH: Dict<string>;
  FR_NOTIF: [string, string][];
  FR_REP: { id: string; t: string; d: string; h: string; ic: string }[];
  FR_SAMPLE: Dict<[string, string, string, string, number][]>;
  FR_SRCG: [string, string[], string][];
  /** state → [label, chip class …] */
  FR_ST: Dict<[string, string]>;
  FR_TG: [string, string, string, string, string][];
  FR_XF: Xf[];
  FR_XTYPES: Dict<SrcType>;
  FXD: Dict<Fixed>;
  GATES: string[];
  HANDOFF_MODEL: Row3[];
  HARD_RULES: string[];
  HOME_LABEL: Dict<string>;
  /** language → English text → translation */
  I18N: Dict<Dict<string>>;
  IDP_ROLES: string[];
  JG: { n: number }[];
  JG_NEXT: string[];
  JMAP: number[];
  JSTEPS: JourneyRow[];
  JSTEPS_AF: JourneyRow[];
  LR_MODELS: Dict<LrModel>;
  MAP_TARGET: Dict<string>;
  MODELS: ModelRow[];
  MONTHS: string[];
  NAV: NavGroup[];
  NOWF: string;
  PAGES: Dict<PageDef>;
  PERM_ALIAS: Dict<string>;
  RATE_CARD: { id: string; carrier: string } & Dict<unknown>;
  RB_AV: Dict<string>;
  RB_SECS: Dict<string[]>;
  REQ_KIND: Dict<string>;
  RG_CONT: Dict<string>;
  RG_CUR: Dict<[string, number, string, string]>;
  RG_LANG: [string, string][];
  RG_TZ: [string, string][];
  RISK_LABEL: Dict<string>;
  ROLE_POLICY: Dict<RolePolicy>;
  ROUTES: Route[];
  /** state → [label, chip class] */
  RUN_ST: Dict<[string, string]>;
  SAMPLE_CSV: string;
  SH: Dict<string>;
  SITES: { id: string; name: string }[];
  SRC_CATS: Dict<string>;
  SRC_CAT_NOTE: Dict<string>;
  SRC_TYPES: Dict<SrcType>;
  STEP_TPL: Dict<string[]>;
  ST_PH: Phase[];
  TBL_AVAIL: Dict<TableSuggestion[]>;
  TBL_MODELS: Dict<TableModel>;
  TENANTS: string[];
  TOOLS: Tool[];
  WF_STC: Dict<string>;
  WF_STL: Dict<string>;
  XF: (Xf & { fileIn?: boolean })[];
}
