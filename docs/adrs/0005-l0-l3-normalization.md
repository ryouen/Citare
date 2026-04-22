# ADR 0005: claim を L0-L3 の 4 層で正規化する

- **Status**: Accepted
- **Date**: 2026-04-23

## Context

claim をどう表現するか。候補:

1. 自然言語テキストのみ（`source_text` 相当）
2. RDF トリプル (subject / predicate / object) のみ
3. 構造化 JSON のみ
4. 上記の組み合わせ

単一形式ではそれぞれ弱点がある:

- **自然言語のみ**: フィルタ・集約できない。機械可読性ゼロ
- **トリプルのみ**: 数値データや mediator / moderator のような 2 項関係を超える構造を扱えない
- **JSON のみ**: グラフ探索に不向き（SQL の JOIN が JSON パス経由になり遅い）
- **数値のみ**: 概念的意味が失われる

## Decision

**同じ claim を 4 層で保存する**:

| Layer | 形式 | 用途 |
|-------|------|------|
| L0 | 構造化 JSON (`l0_json`) | 機械フィルタ（iv, dv, mediator, moderator, ... による絞り込み） |
| L1 | トリプル（独立 3 カラム） | グラフ走査（SQL の JOIN で高速） |
| L2 | 自然言語（`l2_en`, `l2_ja`） | 人間が読む、AI が引用する |
| L3 | 統計値 JSON (`l3_json`) | 数値比較（効果量、p 値、R²、信頼性係数） |

## Rationale

**原則 4 の「1 つの概念に 1 つの名前」と矛盾しない**: 同じ claim を 4 形式で保存するが、意味レベルの分解は一度しか行わない。同じ L0 から L1/L2/L3 は機械的に導出可能（逆変換はできない）。

### 形式ごとの最適ユースケース

- **L0**: "iv = team_psychological_safety の RELATION を全部持ってこい" — JSON path クエリ or generated column + index で高速
- **L1**: "team_psychological_safety の 2 ホップ先にある概念は？" — `l1_subject = ? JOIN l1_object = ?` のシンプルな SQL
- **L2**: 引用文として AI が文書に埋め込むとき。原文らしさが要る
- **L3**: "d > 0.5 の RCT だけ" / メタアナリシスの統合

### なぜ重複を許すか

冗長だが、ユースケース別に**最速のストレージ**を用意するほうが合計コストが低い。全てを L0 から on-demand 生成すると、検索 / グラフ探索 / 表示の全てが遅くなる。

## Consequences

- ✅ 各ユースケースで最適なストレージ
- ✅ 部分的な更新が可能（L2_ja を後から翻訳でバッチ投入、など）
- ⚠ データ整合性リスク: L0 を更新したが L1 を忘れる、など
  - 解: L0 を source of truth とし、L1/L2_en は抽出プロンプト内で LLM が同時生成
  - L2_ja は独立（別バッチ）
- ⚠ ストレージ増加: 1 claim あたり ~2KB → ~4KB。100 万 claim で 4GB。SQLite で問題なし

## Implementation Notes

- 抽出プロンプトは L0 + L1 + L2_en + L3 を**同時出力させる**。LLM が一貫性を保つのが最速
- L2_ja は初期は null。週次バッチで Sonnet 4.6 で翻訳投入
- validator: L0 と L1 の整合性チェック（iv → l1_subject、dv → l1_object、relation → l1_predicate）を validation ステップで実施

## Alternatives Considered

- **L0 のみ + ビュー**: SQLite で `json_extract()` を generated column にできるので部分的に可能だが、l1_predicate のような命名変換（`positive` → `positively_associated_with`）は計算が必要でビュー化が複雑化。却下。
- **グラフ DB (Neo4j)**: L1 の用途には最適だが、L0/L3 の JSON 保管と統計分析が弱く、運用コストが上がる。v1 では SQLite で十分。将来スケールしたら考える。
