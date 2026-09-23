# Makes the SYNTHETIC test PDFs. All names and facts are invented. Needs: pip install reportlab
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
def doc(path, pages):
    c = canvas.Canvas(path, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(40, y, line)
            y -= 15
        c.showPage()
    c.save()
doc("dc_sentencing.pdf", [
 ["NOTE: PUBLICATION OF NAME, ADDRESS, OCCUPATION OR IDENTIFYING PARTICULARS OF",
  "COMPLAINANT PROHIBITED BY S 203 OF THE CRIMINAL PROCEDURE ACT 2011.",
  "", "IN THE DISTRICT COURT", "AT MANUKAU", "I TE KOTI-A-ROHE", "KI MANUKAU",
  "CRI-2024-092-001234", "[2025] NZDC 18765", "THE KING", "v", "TEST DEFENDANT",
  "Hearing: 14 August 2025", "Appearances: A Prosecutor for the Crown", "B Counsel for the Defendant",
  "Judgment: 14 August 2025", "", "NOTES OF JUDGE A B EXAMPLE ON SENTENCING"],
 ["[1] You appear for sentence on one charge of wounding with reckless disregard,",
  "s 188(2) of the Crimes Act 1961, and one charge of assault under s 9 of the Summary Offences Act 1981.",
  "[12] I adopt a starting point of three years' imprisonment.",
  "[14] I uplift by three months for previous convictions.",
  "[16] You are entitled to 25 per cent for your guilty plea entered at an early stage.",
  "[17] I allow 10 per cent for remorse and 15 per cent for your background under s 27",
  "of the Sentencing Act 2002."],
 ["[20] That leaves an end sentence of 20 months' imprisonment.",
  "[22] As the sentence is less than two years I must consider home detention.",
  "[23] I commute that to 10 months' home detention.",
  "[24] You must pay reparation of $1,500 to the victim.",
  "Judge A B Example", "District Court Judge"]])
doc("dc_civil.pdf", [
 ["IN THE DISTRICT COURT", "AT WELLINGTON", "CIV-2023-085-000321", "[2024] NZDC 5432",
  "BETWEEN EXAMPLE BUILDERS LIMITED", "Plaintiff", "AND SAMPLE PROPERTIES LIMITED", "Defendant",
  "Hearing: 3 March 2024", "Judgment: 21 March 2024", "", "RESERVED JUDGMENT OF JUDGE C D SAMPLE"],
 ["[5] The claim is for $48,000 under the Construction Contracts Act 2002.",
  "[30] Judgment is entered for the plaintiff in the sum of $32,500 plus costs."]])
doc("yc_decision.pdf", [
 ["IN THE YOUTH COURT", "AT HAMILTON", "[2024] NZYC 101", "NEW ZEALAND POLICE v YP",
  "Judgment: 2 May 2024", "DECISION OF JUDGE E F TEST"], ["[1] Some text about the young person."]])
