# ADR 0001: MIT License を採用する

- **Status**: Accepted
- **Date**: 2026-04-23
- **Deciders**: 石井遼介

## Context

"Built with Opus 4.7" ハッカソンのルール (`rule_text.txt`) に以下が明記されている:

> **Open Source**: Everything shown in the demo must be fully open source. This includes every component — backend, frontend, models, and any other parts of the project — published under an approved open source license.

「approved open source license」は OSI-approved license を指す。候補は MIT / Apache 2.0 / BSD-3-Clause / GPL-3.0 など。

## Decision

**MIT License を採用する**。

## Rationale

1. **OSI-approved**: ハッカソンルール準拠
2. **最も単純**: 依存者が読む手間が最小。ハッカソン審査員・将来のコントリビューターにとって障壁ゼロ
3. **Python エコシステムとの親和性**: FastAPI, pydantic, MCP SDK など主要依存が MIT / BSD 系。ライセンス非互換問題が起きにくい
4. **商用利用の柔軟性**: 将来 Citare Graph のサーバー側で有料サービスを提供する余地を残す（Apache 2.0 でも可だが MIT の方が短く明快）

Apache 2.0 を選ばなかった理由: 特許グラントは本プロジェクトでは実質的価値が低く、LICENSE ファイルの長さによる心理的障壁を増やしたくない。将来「明示的な特許条項が必要」という要件が出た場合は Apache 2.0 への移行を検討する（MIT → Apache 2.0 は外向きに一方向に互換、逆は不可）。

## Consequences

- ✅ ハッカソンルール準拠
- ✅ 外部貢献者が ContribLicense を気にせず PR できる
- ⚠ 特許防御はない（特許トローリング対策が必要になったら Apache 2.0 に移行）
- ⚠ LICENSE に個人名を書く必要がある（`Copyright (c) 2026 Ryosuke Ishii`）。将来組織に移す場合は `(株)ZENTech` に書き換える

## Implementation

- リポジトリルートに `LICENSE` ファイルを配置済み
- `README.md` にライセンス節を明記
- 各パッケージの `pyproject.toml` に `license = "MIT"` を記載
