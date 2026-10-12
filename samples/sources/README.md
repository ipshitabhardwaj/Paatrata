# Source documents

One file per scheme (PDF or .txt). Every file must have a row in `sources.csv` with its URL, the date
accessed, and whether it is the **primary** notification or a **secondary** summary. Only primary
sources should back claims in the pitch. The compiler and the UI read `scheme_id` from this file, so
compile `ptwadwc_chandigarh.txt` and it lands on scheme `ptwadwc-chandigarh` automatically.

| file | scheme | source type |
|---|---|---|
| oapc_chandigarh.txt | Old Age Pension | secondary summary |
| ptwadwc_chandigarh.txt | Pension to Widows and Destitute Women | secondary summary |
| disabled_pension_chandigarh.txt | Pension to the Disabled Person | secondary summary |
| fsdcwdw_chandigarh.txt | Financial Assistance to Dependent Children of Widows and Destitute Women | secondary summary |
| wpcbocwwb_chandigarh.txt | Widow Pension (Construction Workers Welfare Board) | secondary, partly paraphrased |
| icds_chandigarh.txt | ICDS | secondary summary |

All six were transcribed from publicservicesmap.in (a mirror of myScheme) on 11 Oct 2026. Wording may
differ slightly from the live page. Replace them with department notification PDFs where you can find
them, keep the same `scheme_id`, and re-check the gold file.
