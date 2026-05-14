{\rtf1\ansi\ansicpg949\cocoartf2868
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 # Meeting Summarizer\
\
## \uc0\u54532 \u47196 \u51229 \u53944  \u44060 \u50836 \
\uc0\u54924 \u51032  \u45433 \u51020  \u54028 \u51068 \u51012  \u50629 \u47196 \u46300 \u54616 \u47732  GPT-4o-transcribe\u47196  STT \u48320 \u54872  \u54980 \
GPT-5.4\uc0\u47196  \u54924 \u51032 \u47197 \u51012  \u51221 \u47532 \u54644  \u49324 \u50857 \u51088 \u50640 \u44172  \u48152 \u54872 \u54616 \u45716  \u54028 \u51060 \u54532 \u46972 \u51064 .\
\
## \uc0\u50500 \u53412 \u53581 \u52376 \
1. \uc0\u50724 \u46356 \u50724  \u54028 \u51068  \u51077 \u47141 \
2. 25MB \uc0\u52488 \u44284  \u50668 \u48512  \u54869 \u51064  \u8594  \u52488 \u44284 \u49884  \u52397 \u53356  \u48516 \u54624 \
3. GPT-4o-transcribe\uc0\u47196  STT\
4. \uc0\u53581 \u49828 \u53944  \u44600 \u51060  \u54869 \u51064  \u8594  \u44600 \u47732  Map-Reduce, \u51687 \u51004 \u47732  \u45800 \u51068  \u50836 \u50557 \
5. GPT-5.4\uc0\u47196  \u54924 \u51032 \u47197  \u49373 \u49457 \
6. \uc0\u44208 \u44284  \u54028 \u51068  \u48152 \u54872  (\u53581 \u49828 \u53944  + \u45796 \u50868 \u47196 \u46300 )\
\
## \uc0\u44592 \u49696  \u49828 \u53469 \
- Python\
- OpenAI API (gpt-4o-transcribe, gpt-5.4)\
- pydub (\uc0\u50724 \u46356 \u50724  \u52397 \u53356  \u48516 \u54624 )\
- python-dotenv\
\
## \uc0\u54028 \u51068  \u44396 \u51312 \
- main.py \uc0\u8594  CLI \u51652 \u51077 \u51216 \
- transcribe.py \uc0\u8594  STT \u47196 \u51649 \
- summarize.py \uc0\u8594  \u50836 \u50557  \u47196 \u51649 \
- utils.py \uc0\u8594  \u52397 \u53356  \u48516 \u54624 , \u54028 \u51068  \u52376 \u47532  \u50976 \u54008 \
- .env \uc0\u8594  API \u53412 \
- .env.example \uc0\u8594  API \u53412  \u53596 \u54540 \u47551 \
- requirements.txt\
\
## \uc0\u44508 \u52825 \
- API \uc0\u53412 \u45716  \u48152 \u46300 \u49884  .env\u50640 \u49436 \u47564  \u44288 \u47532 \
- \uc0\u47784 \u46304  \u54632 \u49688 \u50640  docstring \u51089 \u49457 \
- \uc0\u50640 \u47084 \u45716  try/except\u47196  \u51105 \u44256  \u47749 \u54869 \u54620  \u47700 \u49884 \u51648  \u52636 \u47141 \
- \uc0\u54028 \u51068  \u52376 \u47532  \u54980  \u51076 \u49884  \u54028 \u51068  \u48152 \u46300 \u49884  \u51221 \u47532 \
\
## \uc0\u44552 \u51648 \
- API \uc0\u53412  \u54616 \u46300 \u53076 \u46377  \u51208 \u45824  \u44552 \u51648 \
- \uc0\u51076 \u49884  \u54028 \u51068  \u48120 \u51221 \u47532  \u44552 \u51648 }