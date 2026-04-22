# ADR 0006: causal_strength を JSON + generated columns で格納する

- **Status**: Accepted
- **Date**: 2026-04-23

## Context

`causal_strength` は 4 フィールドのメタデータ:

- `design_basis` (cross_sectional / longitudinal / quasi_experimental / rct / meta_analysis / computational_demonstration / theoretical)
- `author_framing` (causal / associational / suggestive / existence_proof)
- `temporal_precedence` (none / partial / full)
- `manipulation_of_iv` (bool)

格納候補:

1. 4 つの独立カラム
2. 単一 JSON カラム
3. JSON カラム + generated columns で頻出フィールドを index

## Decision

**案 3: JSON カラム + generated columns**。

```sql
causal_strength TEXT,  -- JSON

-- Generated columns (SQLite 3.31+)
design_basis_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL,
author_framing_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing')) VIRTUAL;

CREATE INDEX idx_claims_design_basis ON claims(design_basis_idx);
CREATE INDEX idx_claims_author_framing ON claims(author_framing_idx);
```

## Rationale

1. **プロンプト出力がそのまま DB に入る**: LLM は `causal_strength: {design_basis: ..., author_framing: ...}` を JSON で返す。独立カラムに分解するマッピング層が不要。原則 4（1 つの概念に 1 つの名前）の「APIフィールド名 = DBカラム名」を保つ
2. **将来のフィールド追加が簡単**: `manipulation_intensity` を足したくなっても DDL 変更不要
3. **頻出クエリは高速**: 「RCT のみ」「associational のみ」は `design_basis_idx` / `author_framing_idx` index で高速化
4. **生成カラムはストレージを食わない**: `VIRTUAL` なら値は保存されず、query 時に計算される（index は保存される）

## Consequences

- ✅ プロンプト → DB → API の名前が一貫
- ✅ スキーマ変更なしでフィールド追加可能
- ✅ 頻出クエリは index で高速
- ⚠ JSON 形式の変更（例: rename `manipulation_of_iv` → `iv_manipulated`）時に、既存 JSON の migration が必要 → 移行スクリプトで一括 JSON 書き換え
- ⚠ SQLite のみの機能（`json_extract` + generated columns）→ PostgreSQL 移行時に書き換え必要（PG は `jsonb_path_ops` index が使える、機能的には等価）

## Alternatives Considered

- **4 独立カラム**: クエリは速いが、マッピング層が必要（LLM 出力 → DB 書き込み時、DB → API 時）。原則 4 違反。却下。
- **JSON のみ、generated columns なし**: `design_basis` フィルタが毎回 full scan で遅い。10 万 claim で実測 ~200ms。却下。
