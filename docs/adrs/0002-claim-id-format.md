# ADR 0002: claim_id を `{doi_hash8}-{letter}-{seq}` 形式にする

- **Status**: Accepted
- **Date**: 2026-04-23

## Context

claim_id は以下の経路で外部に露出する:

1. REST API の URL パス: `GET /api/claims/{id}`
2. MCP ツールの入出力: `cite_claim(claim_id=...)`
3. 論文引用: AI アシスタントが生成する文書に埋め込まれる
4. `claim_relations` テーブルの外部キー

候補:
- **A: UUID v4** — 衝突安全、ランダム。長い（36 文字）、人間に覚えにくい、DB 再構築で全部変わる
- **B: 連番 (auto-increment)** — 短いが、DB 再構築でズレる。複数インスタンスでの重複リスク
- **C: 合成 ID** — DOI ハッシュ + テンプレート種別 + 論文内連番

## Decision

**形式: `{doi_hash8}-{template_letter}-{seq}`**

- `doi_hash8`: 論文 DOI の SHA-256 先頭 8 hex
- `template_letter`: `R` (RELATION) / `D` (DEFINITION) / `E` (EXISTENCE_CLAIM) / `M` (META_CLAIM)
- `seq`: 該当論文内での 3 桁連番（`001`, `002`, ...）

例: `a3f7c92e-R-012`

## Rationale

1. **安定性**: DOI が同じなら ID が再計算可能。DB 再構築で ID が変わらない
2. **短さ**: 16 文字（UUID の 36 文字に対して半分以下）
3. **人間可読**: template_letter で種別が一目でわかる（デバッグ、ログ、URL で便利）
4. **部分的に意味を持つ**: 同じ論文の claim は prefix が揃うのでソートで自然にグルーピングされる
5. **衝突不可**: DOI は一意、同一論文内で seq も一意 → 全体で一意

## Trade-offs

- ⚠ DOI を持たない Level A の論文は扱えない（現状なし、将来書籍格納時に要検討）
- ⚠ DOI が訂正される稀ケースで ID が変わる → `revision_history` で旧 ID を記録して対応
- ⚠ SHA-256 の 8 hex（32 bit）は理論上 2^32 論文で衝突するが、2^16 (~65k) 論文以降で birthday paradox が顕在化。1 万論文規模なら無視できる。10 万本を超えたら 12 hex に拡張する（実装時に将来拡張パスを用意）

## Implementation

```python
# packages/citare-core/src/citare_core/ids.py
import hashlib

TEMPLATE_LETTER = {
    "RELATION": "R",
    "DEFINITION": "D",
    "EXISTENCE_CLAIM": "E",
    "META_CLAIM": "M",
}

def claim_id(doi: str, template_type: str, seq: int) -> str:
    doi_hash = hashlib.sha256(doi.encode()).hexdigest()[:8]
    letter = TEMPLATE_LETTER[template_type]
    return f"{doi_hash}-{letter}-{seq:03d}"
```

テストは「同じ DOI + template + seq → 同じ ID」と「異なる DOI → 異なる prefix」の 2 本。

## Alternatives Considered

- **UUID v4**: 安全だが URL が長く、デバッグで ID を書き写すのが苦痛。却下。
- **auto-increment**: DB 依存で移行が難しい。却下。
- **DOI + suffix そのまま**: DOI に `/` が含まれ URL エンコーディングが必要、長すぎる。却下。
