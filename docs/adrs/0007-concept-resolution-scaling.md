# ADR 0007: 概念照合は段階的にスケールする

- **Status**: Accepted
- **Date**: 2026-04-23

## Context

Citare では `iv` / `dv` 等に使う概念名は `concepts.canonical_name` と一致させる必要がある（原則 4: 1 つの概念に 1 つの名前）。

新しい claim を抽出するとき、LLM に「この iv/dv はすでに登録されている概念のどれに当てはまるか」を判断させる必要がある。

方式候補:

1. **フルリスト渡し**: `concepts` テーブルの `canonical_name` 全てをプロンプトに列挙
2. **Embedding + top-k retrieval**: claim の iv/dv 候補を embedding に変換 → top-k を LLM に渡す
3. **MCP Sampling**: クライアント側 LLM に register_claims が照合タスクを投げる

各方式のスケール特性:

| 方式 | concepts 数上限 | コスト | 実装難度 |
|------|---------------|--------|---------|
| 1. フルリスト | ~1,000 | 低 | 低 |
| 2. embedding + top-k | 100 万+ | 中 | 中 |
| 3. MCP Sampling | 依存先の LLM に依存 | 低（Citare 側） | 高 |

## Decision

**段階的にスケールする**。

### Phase 1（v1、concepts < 1,000）

方式 1: フルリスト渡し + 80% 文字列類似度チェック

```
1. 抽出プロンプトに concepts.canonical_name 全リストを渡す
2. LLM が既存概念を選ぶ or new_concept_proposed: true を返す
3. new_concept_proposed 時、文字列類似度 (Levenshtein) で既存との比較
   - ≥ 80%: 既存にマッピング、警告ログ
   - < 80%:  新規として自動登録、週次バッチレビュー対象
```

### Phase 2（concepts が ~1,000 を超える段階）

方式 2: embedding + top-k

```
1. 新しい iv/dv 候補を OpenAI text-embedding-3-small で埋め込み
2. concepts の埋め込みと cos sim で top-20 を抽出
3. top-20 を LLM に渡して選択 or new_concept_proposed
```

### Phase 3（MCP 対応）

方式 3: MCP Sampling

```
register_claims が MCP Sampling でクライアント LLM に照合タスクを送る
（サーバー側の LLM コスト負担を下げる）
```

## Rationale

1. **v1 でフルリストが成立する根拠**: 初期ドメインは心理学中心で、concepts は 500-800 個程度で飽和する見込み。1,000 到達後は embedding に移行
2. **80% 類似度の脆さを認識**: "team_psychological_safety" と "team-level PS" は Levenshtein では遠いので、embedding 方式が本来は最初から正しい。ただし v1 では「bootstrap の速さ」を優先
3. **embedding 化は遅らせる**: v1 時点では concepts の数が少なく、embedding 計算のコスト / インフラ追加が ROI に合わない

## Consequences

- ✅ v1 は実装最小で動く
- ✅ Phase 2 への移行パスが明確（embedding カラムを concepts に足し、バッチで埋め込み生成）
- ⚠ Phase 1 で "team_psychological_safety" と "team-level_PS" が別概念として登録される事故が起きうる → 週次バッチレビューで検出 + マージ
- ⚠ concepts マージ時に過去の claim の iv/dv をリネームする migration が必要 → `revision_history` に記録しつつ実施

## Implementation Notes

- Phase 2 対応の準備: `concepts` テーブルに最初から `embedding BLOB` カラムを用意しておく（v1 では全 NULL）
- Phase 1 バッチレビューは `scripts/concept_similarity_report.py` で週次生成し、人間が確認

## Alternatives Considered

- **最初から embedding**: 実装コストが高く、v1 のクリティカルパスに入れたくない。却下（ただし Phase 2 で必ずやる）
- **LLM を使わず文字列ベースでのみ照合**: 類似概念の取りこぼしが多すぎる。却下
