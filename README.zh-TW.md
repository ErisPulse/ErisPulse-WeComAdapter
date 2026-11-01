[English](README.en.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-WeComAdapter" />

# ErisPulse-WeComAdapter

**ErisPulse 企業微信適配器 — 回調接收、應用訊息與通訊錄 API**

<p>
  <a href="https://pypi.org/project/ErisPulse-WeComAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-WeComAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-WeComAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## Features

- **Multi-account** — one WeCom self-built app per account, independent access_token caching
- **Webhook receive** — callback routes registered automatically, URL verification and message push handled
- **Encryption** — WeCom AES-256-CBC encrypt/decrypt and signature verification via `cryptography`
- **Rich message types** — text, Markdown, image, voice, video, file, news, text-card, template-card
- **OneBot12 standard** — events follow the spec; platform extensions prefixed `wecom_`

## Install

```bash
epsdk install WeComAdapter
```

## Links

- [ErisPulse main repo](https://github.com/ErisPulse/ErisPulse)
- [Module development guide](https://www.erisdev.com/#docs/developer-guide/README.md)

> The full documentation (configuration tables, event mappings, API reference) is in Chinese: switch to **简体中文** above.

## License

MIT
