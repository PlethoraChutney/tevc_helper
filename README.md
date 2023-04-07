# ABF Plotter

## Usage

Install from `requirements.txt`:

`python -m pip install -r requirements.txt`

Process files and launch to server:

```
cd /wherever/your/files/are
python /wherever/this/script/is/tevc_helper.py .
```

Your terminal will let you know that thing are being processed, then
it'll tell you to open the web interface. From there, you can click
a given .abf file and see the traces. Highlighting a region in the left
trace will update the mean/min/max plots on the right. Hovering over
the mean/min/max will give you the exact value.

CSVs are also saved in the same directory as the .abfs for future use.

Happy to hear any suggestions or requests!
