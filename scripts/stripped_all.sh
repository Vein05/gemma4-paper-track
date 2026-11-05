cd <repo>/scripts
for t in gemma4-31b gpt-oss-20b qwen35-9b glm47-flash qwen3-coder gpt-oss-120b glm-4.5 kimi-k2 llama-4-maverick; do
  ( python3 stripped_rescore.py run --tag $t --workers 24 >> logs/stripped_$t.log 2>&1
    python3 stripped_rescore.py run --tag $t --workers 24 --redo-unparsed >> logs/stripped_$t.log 2>&1
    echo "$t done" >> logs/stripped_all.log ) &
done
wait
echo ALL_DONE >> logs/stripped_all.log
