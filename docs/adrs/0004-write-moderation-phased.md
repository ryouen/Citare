# ADR 0004: 書き込みモデレーションは段階導入する

- **Status**: Accepted
- **Date**: 2026-04-23

## Context

`register_claims` をオープンにすると、以下のリスクがある:

- 悪意あるエントリ（捏造 claim、存在しない論文、スパム）
- 低品質エントリ（LLM の confidence が低いまま投入される）
- `new_concept_proposed` 濫用による concepts テーブル汚染

一方、厳格なモデレーションは以下のコストを生む:

- 人間承認のボトルネック → Wikipedia モデルの利点喪失
- v1 プロトタイプ段階では user 数が少なく、過剰設計

## Decision

**段階導入する**。

### Phase 1（v1、今〜20 ユーザー未満）

- **招待制 API key のみ**
- モデレーションなし（実質プロジェクトオーナー + 少数信頼ユーザーのみが書き込み）
- `confidence_level` / `confidence_score` による自動タグ付けで品質表示

### Phase 2（ユーザー 20 人以上、Phase 1 で具体的な品質問題が観測されたら前倒し）

- `submitter_id` を claim に記録（誰が書いたか追跡）
- per-key quota: 100 claim/日 など
- 抜き打ち `human_verified` レビュー（全体の 5% サンプリング）
- スパム自動検知:
  - 同一 claim の大量登録（重複ハッシュ）
  - 異常な `new_concept_proposed` 率（通常 10-20%、50% 超は要注意）
  - DOI 検証失敗率が高い submitter

### Phase 3（コミュニティ化、100 ユーザー超）

- コミュニティモデレーター制度
- `propose_correction` MCP ツールでオープンな訂正提案
- claim の `status`: `active` / `flagged` / `retracted`

## Rationale

1. **v1 で過剰設計しない**: ユーザー 20 人未満ならオーナーが目を通せる
2. **前倒し条件を明示**: Phase 1 でも「具体的な品質問題が観測されたら前倒し」。基準は主観でよい
3. **submitter_id は Phase 2 で後付け可能**: `claims` テーブルに `submitter_id TEXT` を最初から入れておき、Phase 1 では常に `owner` を入れる

## Consequences

- ✅ v1 実装が単純（API key 発行スクリプトだけあればよい）
- ✅ Phase 2 移行時のスキーマ変更が最小
- ⚠ Phase 1 でオーナー以外が低品質 claim を入れても止められない → 招待する相手を選ぶ（人間ポリシー）
- ⚠ API key が漏洩すると大量投入される → rate limit は Phase 1 でも入れる（10 claim/分 程度の軽い上限）

## Implementation Notes

- `claims.submitter_id TEXT` を最初から schema に入れる
- API key 管理: `infra/migrations/000X_create_api_keys.sql` で `api_keys(key_hash, owner, created_at, last_used_at, daily_quota, status)` テーブル
- v1 のレート制限: FastAPI の `slowapi` で `10/minute` の簡易制限のみ
