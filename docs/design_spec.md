# Citare Design Specification

- **Version**: 1.0.0
- **Status**: Draft (for Built-with-Opus-4.7 hackathon submission)
- **Date**: 2026-04-23
- **Domain**: citare.dev
- **Hackathon compliance**: 本ドキュメントおよび本プロジェクトのコード・プロンプトは、すべてハッカソン期間中に新規に起こす

---

## 0. このドキュメントの位置付け

Citare の全設計を「全体から部分へ」構造化した単一参照文書。設計判断の**理由**と**根拠**を含む。実装コードとこのドキュメントが食い違った場合は、このドキュメントを正とし、コード or ドキュメントを修正する。

周辺ドキュメント:
- `docs/architecture.md` — 全体図・データフロー
- `docs/api_reference.md` — REST API 詳細
- `docs/extraction_guide.md` — 抽出プロンプト運用
- `docs/legal/pdf_fair_use_policy.md` — 本文引用と PDF 保管方針
- `docs/adrs/` — 個別設計判断の Architecture Decision Records

---

# Part 1: ビジョンと原則

## 1.1 Citare とは何か

学術論文の中にある「主張 (claim)」を、機械が読める形で構造化・蓄積する知識グラフ DB。

> **"DOI is for papers. Citare is for claims."**

名前: ラテン語 *citāre*（召喚する、呼び出す、引用する）に由来。

### ブランド構成

```
Citare         — プロジェクト全体の総称
Citare MCP     — MCP サーバー（uvx citare-mcp で配布）
Citare Graph   — 知識グラフ DB + REST API（citare.dev）
```

## 1.2 設計を貫く 4 原則

全ての設計判断は以下に照らして行う。

**原則 1: 一度構造化すれば、二度と原論文に戻らせない**
- 情報の削減は慎重に。全ベースラインの数値、サンプル情報、原文テキストを保持する
- 「原論文の Table を参照してください」は設計の失敗

**原則 2: 因果の取り違えを構造的に防止する**
- `causal_strength`（4 項目）が最重要メタデータ
- `author_generalization` で Discussion の抽象化を検出
- `verification_status` で検証済み知見と未検証仮説を区別
- これらが Citare の差別化機能の核心であり、他のどの学術インフラにもない

**原則 3: LLM が出力しなければ DB に入らず、後から補完するには論文を再読する必要がある**
- プロンプトに含めないフィールドは事実上存在しないのと同じ
- 「Phase 2 で追加」は危険。データは抽出時に最大限記録する

**原則 4: 1 つの概念に 1 つの名前。どこを見ても同じ名前**
- プロンプト出力、DB カラム、API フィールド名を一致させる
- マッピングが毎回発生するのは設計の問題
- `concepts` テーブルで iv/dv の表記揺れを構造的に防止

## 1.3 解決する課題

| # | 課題 | Citare の解 |
|---|------|-------------|
| 1 | 同じ論文を世界中で AI が何万回も読む | 一度構造化すれば再利用 |
| 2 | "associated with" を "causes" と書く | `causal_strength` メタデータで構造的防止 |
| 3 | 媒介モデルの一部だけ引用 | `incompleteness_category` 展開で文脈不足を警告 |
| 4 | 存在しない知見を AI が生成 | `source_text`（原文）で根拠チェック |
| 5 | Edmondson の PS と Kahn の PS を混同 | `concepts` テーブルで曖昧性解消 |
| 6 | Method の SWLS を Discussion で "ウェルビーイング" と書く | iv/dv は Method ベース、`author_generalization` で抽象化を記録 |
| 7 | 検証済み知見と著者の仮説の混同 | `verification_status` で区別 |

## 1.4 格納対象

```
Level A: 査読済み論文（DOI 付き）   → Extract + Store + Public
Level B: プレプリント              → Extract + Store (flagged) + Public
Level C: 未発表ドラフト            → Extract + Return + NOT stored
Level D: 政策文書・報告書          → Extract + Return + NOT stored
```

## 1.5 Citare が提供しないもの

- ❌ 論文の要約サービス（claim を構造化する）
- ❌ 検索エンジン（Semantic Scholar 等が既にある）
- ❌ AI が論文を書くサービス（正確な引用を**支援**する）
- ❌ 効果量の実質的意義の判定（分野依存のため一律判定は危険）

---

# Part 2: データモデル

## 2.1 `papers`

```sql
CREATE TABLE papers (
    doi TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,          -- JSON array
    year INTEGER,
    venue TEXT,
    paper_type TEXT,                -- empirical / conceptual / review / meta_analysis / book / book_chapter
    domain TEXT                     -- 雑誌記事や commentary は conceptual に含める（媒体ではなく内容で判断）
);
```

**DOI を持たない書籍・政策文書の扱い**: v1 では Level A に入れない（Level D として Extract 結果のみ返す）。将来、本格的に格納する場合は `papers.id` を合成 ID（例: `book:${ISBN}`）に変え `doi` を nullable に降格する。v1 では発生しないため現状の DOI PK で固定。

## 2.2 `claims` — Citare の核心

### 2.2.1 claim_id 形式（確定）

```
{doi_hash8}-{template_letter}-{seq}
```

- `doi_hash8`: 論文 DOI の SHA-256 先頭 8 hex（例: `a3f7c92e`）
- `template_letter`: `R` (RELATION) / `D` (DEFINITION) / `E` (EXISTENCE_CLAIM) / `M` (META_CLAIM)
- `seq`: その論文内での 3 桁連番（001, 002, …）

例: `a3f7c92e-R-012`

選定理由: UUID より人間可読、短い、API URL に直接露出可能、DOI が同じなら ID が安定再計算可能。詳細は `docs/adrs/0002-claim-id-format.md`。

### 2.2.2 テンプレート（4 種）

**DEFINITION — 「X とは何か」**

概念的定義を記録する。操作的定義のみの場合は DEFINITION claim にせず `measurement_methods` に記録。

```json
{
  "template_type": "DEFINITION",
  "l0_json": {
    "concept": "team_psychological_safety",
    "key_elements": ["shared_belief", "interpersonal_risk_taking", "team_level"],
    "distinguished_from": ["trust", "group_cohesion"],
    "new_concept_proposed": true
  }
}
```

- `verification_status` は DEFINITION には `null`
- `new_concept_proposed` は既存概念リストにない場合のみ `true`、リスト内の概念の場合はフィールド自体を省略

**RELATION — 「X と Y の間に関係がある」**

最も数が多い。`causal_strength` メタデータが必須。iv/dv は Method セクションの測定に基づく。

```json
{
  "template_type": "RELATION",
  "l0_json": {
    "iv": "team_psychological_safety",
    "dv": "team_learning_behavior",
    "relation": "positive",
    "mediator": null,
    "moderator": null,
    "validity_threats": [],
    "author_generalization": null,
    "new_concept_proposed": true
  }
}
```

著者が Discussion で使う抽象ラベルと Method の測定が異なる場合:

```json
"author_generalization": {
  "discussion_label": "wellbeing",
  "actual_measure": "individual_life_satisfaction_diener_swls",
  "note": "Author writes 'wellbeing' in Discussion but measured SWLS in Method"
}
```

**EXISTENCE_CLAIM — 「X が存在する / 観察された」**

```json
{
  "template_type": "EXISTENCE_CLAIM",
  "l0_json": {
    "phenomenon": "between_team_ps_variation",
    "evidence": "ICC=.39, significant between-group variance"
  }
}
```

**META_CLAIM — 「複数の研究を統合した知見」**

```json
{
  "template_type": "META_CLAIM",
  "l0_json": {
    "integrated_finding": "...",
    "synthesis_type": "quantitative_meta_analysis / qualitative_synthesis / theoretical_integration",
    "k": 136,
    "N_total": 13914
  }
}
```

### 2.2.3 多層正規化（L0-L3）

同じ主張を 4 形式で保存する。使う場面ごとに最適な形式が異なるため。詳細は `docs/adrs/0006-l0-l3-normalization.md`。

**L0（構造化テンプレート）— 機械がフィルタするため**

```json
{"iv": "team_psychological_safety", "dv": "team_learning_behavior", "relation": "positive"}
```

iv/dv の命名は `concepts` テーブルの `canonical_name` と一致させる。リストにない場合は `"new_concept_proposed": true` を付けて新規提案。

**L1（トリプル）— グラフを辿るため**

```
l1_subject   = "team_psychological_safety"
l1_predicate = "positively_associated_with"
l1_object    = "team_learning_behavior"
```

独立カラムなので SQL の JOIN で高速にグラフ走査可能。

**L2（自然言語）— 人間が読むため**

```
l2_en: "Team psychological safety is positively associated with learning behavior (B=.76, p<.01)."
```

`l2_ja` は抽出時に生成せず、バッチ処理で後から生成する。DB にはカラムを維持。将来 L2 の多言語は「翻訳」ではなく「日本語独立抽出」に切り替える余地を残す（コスト倍だが概念ニュアンスの劣化を避けられる）。

**L3（統計値）— 数値を比較するため**

```json
{
  "effect_size": 0.76,
  "effect_size_type": "B",
  "p": "<.01",
  "r_squared": 0.63,
  "r_squared_type": "adj_r_squared",
  "mediation": {"direct_effect": 0.25, "direct_p": "=.42"},
  "models": [{"label": "Model 1", "r_squared": 0.79}],
  "formal": {"equation": "H = -Σ p log p", "variables": {}},
  "additional": {},
  "reliability": {"alpha": 0.85, "icc": 0.39}
}
```

- `effect_size_type` 標準リストは付録 A
- `B_unstandardized` は使用しない。`"B"` に統一
- リストにない指標は `additional` に記録
- `models` 配列は**全ベースラインを記録する**（原則 1）。メタアナリシスの横断的集約で必要

### 2.2.4 原文保存 (`source_text`)

```
source_text:    "a shared belief held by members of a team that..."
source_page:    354
source_section: "Team Psychological Safety"
```

- 1-3 文の直接引用（fair use 範囲）
- `source_page` は**印刷ページ番号**（PDF ビューアのページ番号ではない）
- 詳細な fair use ポリシーは `docs/legal/pdf_fair_use_policy.md`

### 2.2.5 因果の強さ (`causal_strength`)

RELATION のみに適用。Citare の最も重要な差別化要因。**JSON カラムとして格納**し、プロンプト出力がそのまま DB に入る設計。

```json
{
  "design_basis": "cross_sectional / longitudinal / quasi_experimental / rct / meta_analysis / computational_demonstration / theoretical",
  "author_framing": "causal / associational / suggestive / existence_proof",
  "temporal_precedence": "none / partial / full",
  "manipulation_of_iv": true
}
```

**Generated Columns で頻出クエリを最適化**（SQLite 3.31+）:

```sql
design_basis_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL,
author_framing_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing')) VIRTUAL;

CREATE INDEX idx_claims_design_basis ON claims(design_basis_idx);
CREATE INDEX idx_claims_author_framing ON claims(author_framing_idx);
```

「RCT のみ」「縦断研究のみ」のフィルタが index 付きで高速。詳細は `docs/adrs/0007-causal-strength-as-json.md`。

### 2.2.6 検証ステータス (`verification_status`)

```
verified_in_paper:  この論文内でデータにより検証
proposed_in_paper:  著者が提案したが、この論文では検証していない
null:               DEFINITION テンプレートの場合
```

### 2.2.7 エビデンスタイプ (`evidence_type`)

```
meta_analysis / rct / quasi_experimental / longitudinal_field /
cross_sectional_field / qualitative_field / computational_demonstration /
theoretical_derivation / theoretical_integration / re_interpretation /
expert_framework / conceptual_argument
```

### 2.2.8 信頼度 (`confidence`)

```
confidence_level: mechanical / llm_extracted / llm_low_conf / human_verified / human_corrected
confidence_score: 0.0-1.0
```

Wikipedia モデル: LLM 抽出結果は `confidence` 付きで即 DB に入る。人間確認はボトルネックにしない。

### 2.2.9 Method メタデータ (`method_metadata`)

```json
{
  "sample_size": 51,
  "unit_of_analysis": "team",
  "industry": "mixed",
  "country": "US",
  "study_design": "cross-sectional survey + archival"
}
```

命名: `sample_n` は「サンプルの例」と誤読されうるため `sample_size`。

### 2.2.10 抽出プロンプトバージョン (`extraction_prompt_version`)

```
extraction_prompt_version: "1.0.0"
```

どのプロンプトバージョンで抽出された claim かを claim ごとに記録。プロンプト進化時に**再抽出対象の特定**が可能。プロンプト本体は `packages/citare-extract/prompts/v{version}/extraction.md` で凍結保存。

### 2.2.11 `claims` 全カラム

```sql
CREATE TABLE claims (
    id TEXT PRIMARY KEY,              -- {doi_hash8}-{letter}-{seq}
    paper_doi TEXT REFERENCES papers(doi),
    template_type TEXT NOT NULL,

    l0_json TEXT,
    l1_subject TEXT, l1_predicate TEXT, l1_object TEXT,
    l2_en TEXT, l2_ja TEXT,
    l3_json TEXT,

    source_text TEXT, source_page INTEGER, source_section TEXT, source_paragraph TEXT,

    evidence_type TEXT,
    verification_status TEXT
        CHECK(verification_status IN ('verified_in_paper','proposed_in_paper') OR verification_status IS NULL),

    causal_strength TEXT,          -- JSON (design_basis, author_framing, temporal_precedence, manipulation_of_iv)
    method_metadata TEXT,          -- JSON (sample_size, unit_of_analysis, industry, country, study_design)

    model_hub BOOLEAN DEFAULT 0,
    confidence_level TEXT, confidence_score REAL,

    extraction_prompt_version TEXT,

    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Generated columns (SQLite 3.31+)
    design_basis_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL,
    author_framing_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing')) VIRTUAL
);

CREATE INDEX idx_claims_design_basis ON claims(design_basis_idx);
CREATE INDEX idx_claims_author_framing ON claims(author_framing_idx);
CREATE INDEX idx_claims_paper ON claims(paper_doi);
CREATE INDEX idx_claims_subject ON claims(l1_subject);
CREATE INDEX idx_claims_object ON claims(l1_object);
```

## 2.3 `claim_relations`

```sql
CREATE TABLE claim_relations (
    source_id TEXT REFERENCES claims(id),
    target_id TEXT REFERENCES claims(id),
    relation_type TEXT NOT NULL,
    incompleteness_category TEXT DEFAULT 'none'
        CHECK(incompleteness_category IN (
            'effect_disappears_under_control','hub_component',
            'boundary_condition','extends_prior_definition','none')),
    context TEXT,
    confidence_score REAL,
    PRIMARY KEY (source_id, target_id, relation_type)
);
```

### 関係タイプ（9 種）

```
part_of_model, supports, extends, contradicts, qualifies,
replicates, aggregates, background, apparent_tension
```

### 不完全性 (`incompleteness_category`)

```
effect_disappears_under_control — 統制すると効果が消える。展開: 必須、2 ホップ
hub_component                   — 媒介/調整モデルの構成要素。展開: 必須、1 ホップ
boundary_condition              — 境界条件あり。展開: 推奨、1 ホップ
extends_prior_definition        — 先行定義を拡張。展開: 任意
none                            — 単独で完全。展開: 不要
```

## 2.4 `paper_references`

```sql
CREATE TABLE paper_references (
    citing_doi TEXT REFERENCES papers(doi),
    cited_doi TEXT,
    cited_title TEXT,
    PRIMARY KEY (citing_doi, cited_doi)
);
```

論文単位（claim 単位ではない）。用途:
- cross-paper relation 検出のフィルタ
- 被引用分析

記録基準: 本文中で claim の根拠や構成要素として使われている文献のみ。括弧内列挙のみの文献は記録しない。1 論文あたり 10-25 件が目安。

## 2.5 非 claim エンティティ

### THEORY (`theories`)

claim 群を束ねるコンテナ。type: `theory` / `theoretical_model` / `framework`。

判定基準: (1) 3+ claim を組織、(2) メカニズムを含む、(3) 仮説を導出可能。論文から抽出するのは**明示的に名前がつけられた理論のみ**。

### MEASUREMENT_METHOD (`measurement_methods`)

```json
{
  "id": "edmondson_7item_ps",
  "name": "Edmondson's Team Psychological Safety Scale",
  "subtype": "questionnaire_scale",
  "measures": "team_psychological_safety",
  "details": {
    "item_count": 7,
    "response_scale": "7-point Likert",
    "reverse_items": [1, 3, 5],
    "reliability_reported": {"alpha": 0.82},
    "original_source": "Edmondson, 1999",
    "copyright_status": "public"
  }
}
```

概念の定義状態（原則 3「抽出時に最大限記録」）:

```
概念的定義あり + 操作的定義あり → DEFINITION claim + measurement_methods
概念的定義なし + 操作的定義あり → measurement_methods のみ（defining_claim_id = null）
  ★ measurement_methods が事実上の操作的定義として機能
概念的定義なし + 操作的定義なし → concepts テーブルに名前だけ
```

`reverse_items` と `reliability_reported` は DEFINITION 不在時に操作的定義として機能するため必須。

### HUB_COMPONENTS (`hub_components`)

媒介・調整モデルの構成関係を明示するジャンクションテーブル。

```sql
CREATE TABLE hub_components (
    hub_id TEXT REFERENCES claims(id),       -- 媒介/調整モデル全体を代表する claim
    component_id TEXT REFERENCES claims(id),  -- 構成要素となる claim (IV→M, M→DV など)
    role TEXT NOT NULL,                       -- iv_m_link / m_dv_link / moderator_link / direct_effect
    PRIMARY KEY (hub_id, component_id, role)
);
```

用途: `incompleteness_category = 'hub_component'` のときに「どの hub の構成要素か」を辿るための明示的リンク。`claim_relations` の `part_of_model` 関係を補強する。

## 2.6 `concepts`

```sql
CREATE TABLE concepts (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    level_of_analysis TEXT,
    domain TEXT,
    defining_claim_id TEXT REFERENCES claims(id),
    distinguished_from TEXT,         -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **aliases カラムは持たない**。LLM に `canonical_name` リストを渡して選ばせる方式
- **階層 (parent_id) は持たない**。フラット構造
- iv/dv 正規化: 測定方法の違い（self-report / observer-rated）は `concepts` ではなく `measurement_methods` で区別

### iv/dv の level prefix（v1 採用）

```
team_, individual_, organizational_, computational_, architecture_,
channel_, source_, scale_, item_, embedding_,
cognitive_, agent_, safety_, therapeutic_
```

### 概念登録ワークフロー

```
Phase 1（v1, 現在）:
  自動登録 + 文字列類似度チェック（80% 閾値）+ 週次バッチレビュー
  new_concept_proposed: true → 既存との類似度チェック
    ≥ 80% 類似: 既存にマッピング、警告ログ
    <  80%:    新規として自動登録、バッチレビュー対象

Phase 2（v2, concepts が ~1000 を超える段階）:
  embedding + top-k retrieval → リスト化 → LLM が選択
  理由: canonical_name 全リストを prompt に渡すと context 制約で破綻

Phase 3:
  MCP Sampling によるクライアント LLM 照合（register_claims 内）
```

`new_concept_proposed` フラグの意味: 自動登録の入口マーカー + 事後レビュー対象マーカー（人間承認を待つゲートではない）。

詳細は `docs/adrs/0009-concept-resolution-scaling.md`。

## 2.7 将来テーブル（Phase 2 以降）

```sql
-- concept_evolution — バッチ処理、50 本蓄積後に claim_relations から構築
CREATE TABLE concept_evolution (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    year INTEGER,
    claim_id TEXT REFERENCES claims(id),
    event_type TEXT,       -- introduction / refinement / boundary_extension / paradigm_shift
    description TEXT
);

-- theory_concept_roles — バッチ処理、theory × concept × claim の三項関係
CREATE TABLE theory_concept_roles (
    theory_id TEXT REFERENCES theories(id),
    concept_id TEXT REFERENCES concepts(id),
    role TEXT,             -- antecedent / mediator / moderator / outcome / boundary
    based_on_claim TEXT REFERENCES claims(id),
    position_in_chain INTEGER
);
```

その他、運用で追加が確実なテーブル:

```sql
-- revision_history — 訂正履歴
CREATE TABLE revision_history (
    id TEXT PRIMARY KEY,
    claim_id TEXT REFERENCES claims(id),
    action TEXT,           -- created / updated / corrected / retracted
    by_user TEXT,
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- terminological_conventions — 分野固有の命名規則
CREATE TABLE terminological_conventions (
    id TEXT PRIMARY KEY,
    term TEXT NOT NULL,
    community TEXT,        -- social_psychology / organizational_psychology / ML / ...
    convention TEXT,
    contrast_with TEXT,
    source TEXT,
    importance TEXT,       -- high / medium / low
    warning TEXT,
    domain TEXT,
    linked_claims TEXT     -- JSON array
);

-- claims_fts — 全文検索
CREATE VIRTUAL TABLE claims_fts USING fts5(
    id, l2_en, l2_ja, l1_subject, l1_object, source_text,
    content='claims'
);
```

---

# Part 3: 抽出パイプライン

## 3.1 Pre-processing — 3 機能のみ

LLM が主役。Pre-processing は LLM のサポートに限定。

1. DOI 取得 + CrossRef メタデータ
2. References パース + DOI 検証
3. 不要セクション除外（References, Acknowledgements, Author info）

## 3.2 LLM Extraction（主役）

- バージョン管理された extraction prompt (`packages/citare-extract/prompts/v1.0.0/extraction.md`) を使用
- コスト目標: ~$0.07-0.10/論文（Opus 4.7 の価格帯で調整）
- ⚠ **PDF からテキストのみを事前抽出して LLM に渡さない**。テキスト抽出で表・数式が消失する。Opus 4.7 にマルチモーダルで PDF を直接渡す

### セクション優先順位

| 優先度 | セクション | 扱い |
|------|----------|------|
| 1 | Method + Results + Tables | 最も丁寧に。**常にセットで送る** |
| 2 | Abstract + Introduction / Theory | |
| 3 | Discussion | 慎重に。`proposed_in_paper` 扱い |

## 3.3 長い PDF の分割

```
≤ 20 ページ:     分割不要（ターゲットの 95%）
20-40 ページ:    2 分割
40 ページ以上:   セクション単位分割
書籍:            章単位（paper_type = book_chapter）
```

## 3.4 Validation

- JSON schema バリデーション
- claim 数妥当性チェック（例: 0 件は要確認、100 件超は分割漏れ疑い）
- iv/dv と `concepts.canonical_name` の照合
- DOI 検証（CrossRef API）

## 3.5 Cross-paper Relations（データ蓄積後）

```
paper_references で引用関係フィルタ
  → iv/dv 概念一致でマッチング候補を絞り込み
  → LLM で関係判定（supports / contradicts / extends / apparent_tension）
  → claim_relations に登録
```

---

# Part 4: データアクセス

## 4.1 REST API（citare.dev）

| Endpoint | 用途 |
|----------|------|
| `GET /api/claims/search` | claim 検索（Preview、cursor ページネーション） |
| `GET /api/claims/{id}` | claim 詳細（本体のみ、relations は含めない） |
| `GET /api/claims/{id}/relations` | 直接関係（フィルタ可能、Preview 付き） |
| `GET /api/claims/{id}/graph` | N ホップグラフ探索 |
| `GET /api/papers/<path:doi>` | 論文詳細 |
| `GET /api/papers/<path:doi>/claims` | 論文内 claim 一覧 |
| `GET /api/concepts` | 概念一覧 |
| `GET /api/concepts/{id}` | 概念詳細 |
| `GET /api/stats` | DB 統計 |

### API 設計 5 原則

1. **単一責任**: 1 エンドポイント = 1 つの仕事
2. **名前の統一**: API フィールド名 = DB カラム名（省略しない）
3. **Preview/Detail 分離**: リスト系は Preview、個別取得で Detail
4. **フィルタ可能**: 関係系は `type`, `category`, `direction` でフィルタ
5. **ページネーション標準装備**: cursor 方式

## 4.2 MCP (`citare-mcp`)

配布: `uvx citare-mcp`（PyPI 公開）。ツール数は一桁に保つ。

**Phase 1（読み取り専用）**
- `search_claims`
- `get_claim_graph`
- `cite_claim`

**Phase 2**
- `register_claims`
- `process_paper`（MCP Sampling + extraction prompt 配信）
- `propose_correction`

**Phase 3**
- `get_research_gaps`
- `get_concept_evolution`
- `compare_theories`

詳細は `docs/mcp_design.md`（別途）。

## 4.3 自動検出（Phase 2-3）

| カテゴリ | 例 | 実現方式 |
|---------|-----|---------|
| A 機械的 | 矛盾検出、研究ギャップ、欠落リンク | SQL + ルール |
| B 半自動 | 概念進化、構造的類似性 | 埋め込み + LLM 照合 |
| C 兆候 + 人間判定 | パラダイムシフト | 統計指標 + 人間レビュー |

---

# Part 5: PDF の扱い（確定方針）

## 5.1 二層構成

**ユーザー端末で処理する層（デフォルト）**
- ユーザーが自分の PDF をローカルに保持
- MCP 経由で Claude に PDF を渡し、Claude API → 抽出 → Citare に `register_claims`
- Citare サーバーは PDF を保管しない

**サーバー側抽出サービス（有料オプション）**
- ユーザーが PDF をアップロード
- サーバーは一時キャッシュ（数時間〜24時間）
- LLM で抽出し、`claims` を DB に保管
- **抽出完了後に PDF を破棄**。キャッシュからも削除
- 保管されるのは claim データ（＋原文 1-3 文の `source_text` のみ、fair use 範囲）

## 5.2 処理フロー

```
[1] Upload (TLS)
      ↓
[2] Cache (S3 or local disk, encrypted at rest, TTL 24h)
      ↓
[3] Extract (Opus 4.7 multimodal, direct PDF input)
      ↓
[4] Register claims (+ source_text 1-3 sentences per claim)
      ↓
[5] Discard PDF (delete from cache, log deletion timestamp)
      ↓
[6] Return claim_ids to user
```

## 5.3 法的整理

- 出版社の ToS で **本文 PDF のサーバー再配布は基本 NG**
- Citare が再配布するのは抽出結果のみ
- `source_text` は 1-3 文の直接引用で fair use 範囲と解釈
- 詳細は `docs/legal/pdf_fair_use_policy.md` で別途整備

詳細は `docs/adrs/0003-pdf-handling.md`。

---

# Part 6: 書き込み・モデレーション（段階導入）

## 6.1 Phase 1（v1、現在〜20 ユーザー未満）

- **招待制 API key のみ** で `register_claims` 可能
- 厳密なモデレーションは設けない（プロジェクトオーナー + 少数の招待ユーザーのみが書き込み）
- `confidence_level` による自動タグ付けで十分

## 6.2 Phase 2（ユーザー 20 人以上の段階で導入）

- `submitter_id` を claim に記録
- per-key quota（例: 100 claim/日）
- サンプリングで `human_verified` 抜き打ちレビュー
- スパム / 低品質エントリの検知: 同一 claim の大量登録、異常な `new_concept_proposed` 率

## 6.3 Phase 3

- コミュニティモデレーター制度
- `propose_correction` MCP ツールによる訂正提案

詳細は `docs/adrs/0004-write-moderation-phased.md`。

---

# Part 7: 公開戦略

| 対象 | 方針 |
|------|------|
| MCP サーバーコード | **オープンソース (MIT)**、GitHub + PyPI |
| REST API コード | オープンソース (MIT) |
| schema DDL | 公開 |
| Extraction Prompt | 公開（コミュニティ改善提案を受けるため） |
| API 仕様 | 公開（OpenAPI 3.1） |
| Citare Graph データ | citare.dev API で**無料読み取り**。書き込みは API key 認証 |
| 個人ユーザー | 無料 |

**モートは spec ではなく claim データ蓄積とネットワーク効果**。spec を閉じて守るアプローチは採らない。

---

# Part 8: 運用とインフラ

## 8.1 v1 スタック

- **DB**: SQLite（単一ファイル、citare.dev VPS 上）
- **API**: FastAPI（Python 3.11+）
- **MCP**: Python + MCP SDK、`uvx citare-mcp` で配布
- **デプロイ**: VPS（systemd + nginx）

## 8.2 バックアップ

```
backup/
  daily/    — SQLite dump、30 日保持
  weekly/   — 圧縮アーカイブ、1 年保持
  monthly/  — 別リージョンに送信、永久保持
```

## 8.3 マイグレーション

- Alembic ではなく**生 SQL マイグレーション**を `infra/migrations/NNNN_name.sql` で管理（SQLite はスキーマ変更が限定的なため Alembic のメリットが薄い）
- マイグレーション実行ログは `schema_migrations` テーブルに記録

## 8.4 スケーリング方針

- v1: SQLite（〜100 万 claim まで余裕）
- v2（100 万 claim 以上 or 書き込み競合発生時）: PostgreSQL 移行検討
- 読み取り負荷対策: API 前に CDN + ETag

## 8.5 機械学習モデル

| Phase | 状態 |
|-------|------|
| v1（今） | 不要。LLM + Pre-processing で十分 |
| v2（200-500 本） | 文分類モデル（claim 含有文検出）で LLM コスト半減 |
| v3（1000 本以上） | iv/dv 抽出モデル、Table 解析モデル |

---

# Part 9: フォルダ構成（モノレポ + uv workspace）

```
citare/
├── pyproject.toml                    # uv workspace root
├── uv.lock
├── LICENSE                           # MIT
├── README.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
│
├── docs/
│   ├── design_spec.md                ← この文書
│   ├── architecture.md
│   ├── api_reference.md
│   ├── extraction_guide.md
│   ├── mcp_design.md
│   ├── legal/pdf_fair_use_policy.md
│   └── adrs/                         # Architecture Decision Records
│
├── packages/
│   ├── citare-core/                  # schema + pydantic models + concept registry
│   │   ├── src/citare_core/
│   │   │   ├── schema/               # DDL (.sql)
│   │   │   ├── models/               # pydantic: Claim, Paper, Concept ...
│   │   │   ├── concepts/             # canonical_name 照合
│   │   │   └── ids.py                # claim_id 生成
│   │   └── tests/
│   │
│   ├── citare-extract/               # LLM 抽出パイプライン
│   │   ├── src/citare_extract/
│   │   │   ├── preprocess/
│   │   │   ├── prompts/
│   │   │   │   └── v1.0.0/extraction.md
│   │   │   ├── pipeline.py
│   │   │   ├── validators/
│   │   │   └── cli.py
│   │   └── tests/
│   │
│   ├── citare-api/                   # FastAPI、citare.dev
│   │   ├── src/citare_api/
│   │   │   ├── routes/
│   │   │   ├── auth/
│   │   │   ├── pagination.py
│   │   │   └── app.py
│   │   └── tests/
│   │
│   ├── citare-mcp/                   # 独立 PyPI パッケージ
│   │   ├── src/citare_mcp/
│   │   │   ├── server.py
│   │   │   └── tools/
│   │   ├── pyproject.toml
│   │   └── tests/
│   │
│   └── citare-batch/                 # 翻訳・concept_evolution・cross-paper
│       └── src/citare_batch/
│
├── infra/
│   ├── docker/{api.Dockerfile,compose.yml}
│   ├── vps/
│   │   ├── citare-api.service        # systemd
│   │   └── nginx.conf                # citare.dev
│   ├── migrations/
│   └── backup/backup.sh
│
├── data/                             # 原則 gitignored
│   ├── db/citare.db
│   ├── pdfs/                         # ローカル開発者キャッシュ（サーバー非格納）
│   ├── extracts/                     # 生 LLM 出力（デバッグ用）
│   └── fixtures/                     # committed、小さなテスト用
│
├── scripts/                          # 運用ワンショット
│   ├── ingest_batch.py
│   ├── rebuild_fts.py
│   └── concept_similarity_report.py
│
└── tests/e2e/                        # パッケージ横断
```

**重要判断**:
- **モノレポ**: schema が `citare-core` にあり、extract/api/mcp が import する。分割すると schema 変更が 4 箇所同時更新になる
- **`citare-mcp` は独立 `pyproject.toml`**: PyPI release を独自サイクルで回す
- **`infra/` を git 管理**: 再現可能な VPS 構築。シークレットは `.env`（gitignore）で分離
- **`data/` 原則 gitignored**: PDF は法的に再配布できない。DB ファイルはバックアップで別管理
- **`docs/adrs/`**: 「なぜこうしたか」が最も早く腐敗する情報。ADR で凍結

---

# Part 10: ロードマップ

## 10.1 Phase 1（ハッカソン期間、2026-04-21 〜 2026-04-26）

目標: 動くデモで審査を通過する最小構成

- [ ] `citare-core`: schema DDL + pydantic models + claim_id 生成
- [ ] `citare-extract`: extraction prompt v1.0.0 + pipeline + CLI
- [ ] `citare-api`: GET 系 API（search, detail, graph）
- [ ] `citare-mcp`: Phase 1 の 3 ツール（search_claims / get_claim_graph / cite_claim）
- [ ] 50-100 本の論文で動作確認、デモ動画収録
- [ ] `docs/design_spec.md` + ADRs

## 10.2 Phase 2（ハッカソン後、〜2026Q3）

- [ ] citare.dev VPS デプロイ
- [ ] 書き込み API（招待制）
- [ ] `process_paper` MCP ツール（Sampling 統合）
- [ ] Cross-paper relations バッチ
- [ ] L2_ja バッチ生成
- [ ] concepts 〜1,000 規模での embedding 照合に移行

## 10.3 Phase 3（〜2026Q4）

- [ ] ユーザー 20 人超、モデレーション機能導入
- [ ] concept_evolution バッチ
- [ ] 研究ギャップ自動検出（Category A）

## 10.4 Phase 4（2027 以降）

- [ ] 100 万 claim、PostgreSQL 移行検討
- [ ] ML モデル導入（文分類、iv/dv 抽出）
- [ ] 構造的類似性検出（Category B）

---

# 付録 A: `effect_size_type` 標準リスト

**心理学**: `B`, `beta`, `r`, `rho`, `d`, `eta_squared`, `partial_eta_squared`, `omega_squared`, `odds_ratio`, `hazard_ratio`

**ML**: `BLEU`, `accuracy`, `F1`, `perplexity`, `Exact_Match`, `ROUGE`, `AUC`, `MAE`, `MSE`

`B_unstandardized` は使用せず、`B` に統一。リストにない指標は L3 の `additional` に格納。

---

# 付録 B: iv/dv level prefix 一覧

```
team_, individual_, organizational_, computational_, architecture_,
channel_, source_, scale_, item_, embedding_,
cognitive_, agent_, safety_, therapeutic_
```

---

# 付録 C: ADR 一覧

- [0001](./adrs/0001-mit-license.md) MIT License を採用する
- [0002](./adrs/0002-claim-id-format.md) claim_id を `{doi_hash8}-{letter}-{seq}` 形式にする
- [0003](./adrs/0003-pdf-handling.md) PDF はサーバーで一時キャッシュし抽出後破棄する
- [0004](./adrs/0004-write-moderation-phased.md) 書き込みモデレーションは段階導入する
- [0005](./adrs/0005-l0-l3-normalization.md) claim を L0-L3 の 4 層で正規化する
- [0006](./adrs/0006-causal-strength-as-json.md) causal_strength を JSON + generated columns で格納する
- [0007](./adrs/0007-concept-resolution-scaling.md) 概念照合は段階的にスケールする（フルリスト → embedding top-k → MCP Sampling）
