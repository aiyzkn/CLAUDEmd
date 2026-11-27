---
name: file-lock
description: 編集・削除されては困るファイルを OS の機能でロックし、Claude Code 自身を含むプロセスから書き換えられないようにする。ロック・解除・状態確認を行う。「このファイルをロックして」「編集禁止にして」「ロックを外して」で使う。
---

# file-lock

指定したファイルを、OS の機能で書き換えにくい状態にする。ルールやプロンプトによる「編集しないで」という指示と違い、誤操作があっても OS の段階で止まる。

## 使い方

```bash
# Windows
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/file-lock.ps1 lock <パス...>
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/file-lock.ps1 unlock [<パス...>]
powershell -NoProfile -ExecutionPolicy Bypass -File ~/.claude/scripts/file-lock.ps1 status
# Linux / macOS
bash ~/.claude/scripts/file-lock.sh lock <パス...>
bash ~/.claude/scripts/file-lock.sh unlock [<パス...>]
bash ~/.claude/scripts/file-lock.sh status
```

- ディレクトリを指定すると、配下のファイルをすべて対象にする（上限 1000 件）
- `unlock` でパスを省略すると、すべてのロックを外す

## OS ごとの強さ

| OS | 方式 | 書き込み | 削除・改名 | 再起動後 |
|---|---|---|---|---|
| Windows | 常駐プロセスがファイルを読み取り共有のみで開いたままにする | 防ぐ | 防ぐ | 外れる |
| macOS | `chflags uchg` と書き込み権限の削除 | 防ぐ | 防ぐ | 残る |
| Linux（root で実行） | `chattr +i` と書き込み権限の削除 | 防ぐ | 防ぐ | 残る |
| Linux（一般ユーザー） | 書き込み権限の削除のみ | 防ぐ（権限を戻せば書ける） | **防げない** | 残る |

Linux の一般ユーザーでは強いロックをかけられない。`sudo` で回避せず、この制限をユーザーに伝える。

## 守ること

- **ロックを外すのは、ユーザーに指示されたときだけ。** ロックされたファイルの編集が必要になっても、自分の判断で `unlock` しない。どのファイルを何のために編集したいのかを示し、解除してよいかを確認する
- ロック中はユーザー自身のエディタからも保存できない。ロックをかけるときにそのことを伝える
- ロックしたいファイルを他のプロセスが書き込み可能な状態で開いていると、Windows ではロックできないことがある。結果の表示を確認する
