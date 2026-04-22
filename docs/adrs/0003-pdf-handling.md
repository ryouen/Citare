# ADR 0003: PDF はサーバーで一時キャッシュし抽出後破棄する

- **Status**: Accepted
- **Date**: 2026-04-23

## Context

Citare が扱う PDF の扱いには法的・運用的な選択肢がある:

1. サーバーで一切キャッシュしない（ユーザー端末のみ）
2. サーバーで一時キャッシュし抽出後破棄する
3. サーバーで永続保管する

出版社の ToS では本文 PDF のサーバー再配布は基本的に NG。一方、抽出処理中の短時間キャッシュは「処理のための一時コピー」として広く認められる（Anthropic など LLM プロバイダのデータセンターが入力を一時処理するのと同じ）。

## Decision

**二層構成を採用する**:

1. **デフォルト（無料）**: ユーザー端末で PDF を保持 → MCP 経由で Claude に渡す → 抽出結果を Citare に `register_claims` で登録
2. **有料サービス**: サーバーで一時キャッシュ（TTL 24 時間）→ LLM 抽出 → claim 保管 → **PDF 破棄**

**サーバーは PDF を永続保管しない**。

## Rationale

1. **法的リスクの最小化**: PDF の永続保管は出版社 ToS 違反リスクが高い。一時処理は fair use 解釈で受け入れられる
2. **ユーザー利便性**: PDF アップロード → claim 抽出を「やることはキャッシュ＋処理だけ」のシンプルな有料サービスとして提供できる
3. **Citare の価値は claim にあり PDF ではない**: 保管すべきは構造化された claim。原文は `source_text` 1-3 文（fair use）で十分
4. **LLM プロバイダのプラクティスと整合**: Claude API にデータを送ると一時処理される。Citare の挙動はその延長で、ユーザーの理解が得やすい

## Processing Flow

```
[1] Upload (TLS)
      ↓
[2] Cache (encrypted at rest, TTL 24h)
      ↓
[3] Extract (Opus 4.7 multimodal, direct PDF input)
      ↓
[4] Register claims (with source_text 1-3 sentences per claim)
      ↓
[5] Discard PDF (delete + log deletion timestamp)
      ↓
[6] Return claim_ids to user
```

## Consequences

- ✅ 法的リスク最小、運用が単純
- ✅ 有料サービスの価値提案が明確（PDF を預けて claim を受け取る）
- ✅ ストレージコストが予測可能（常に 24h 窓の合計）
- ⚠ 「一度処理した PDF を再処理したい」要望に応えにくい → ユーザーは再アップロード必要
- ⚠ プロンプト改善後に既存 PDF で再抽出ができない → 解: 抽出時の生 LLM 出力 (`data/extracts/`) を保存しておけば、プロンプト変更なしの再処理は可能。プロンプト変更時の再抽出は新規アップロード扱い

## Implementation Notes

- キャッシュストレージ: VPS ローカルディスク（v1）。v2 で S3 互換に移行可能な抽象化を `citare-api/src/citare_api/storage.py` に切る
- 暗号化: at-rest 暗号化（LUKS or ファイルレベル）
- 削除: 抽出完了 or TTL 切れ時に `shred` 相当で消す（復元困難にする）
- ログ: `audit_log` テーブルに `upload_at` / `deleted_at` / `doi` を記録。内容は保存しない

## Legal Documentation

本 ADR とは別に `docs/legal/pdf_fair_use_policy.md` を整備し、以下を明記する:

- 処理対象の法的前提（ユーザーが PDF の利用権限を持つこと）
- fair use 引用範囲（1-3 文、`source_text` カラム）
- 非再配布の宣言
- publisher からの削除要請への対応手順
