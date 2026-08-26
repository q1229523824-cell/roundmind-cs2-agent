@echo off
chcp 65001 >nul
title RoundMind CS2 Agent - DeepSeek
"%~dp0RoundMind-Local-Parser.exe" --enable-deepseek
pause
