import streamlit as st

_ABOUT_MD = """
This website started as a personal tool that lived on my laptop that helped me keep up with literature.
Eventually I wanted access to it from anywhere, so I put it on the internet. It is still primarily a personal tool, 
but you are welcome to check it out, and if you do, I hope you find it useful.
If you have suggestions for how to make it better, please let me know through the contact form (just type something in the "Suggest an article" page.). I would love that!
If you want to see a description of how it works, scroll down to the section "My program/process" below.


### My goal - why did I make this?

I have always struggled to figure out the best way to keep up with the literature as a hospitalist. 
I have tried a lot of different approaches, and I have never been satisfied with any of them.
The main problem is partially unique to hospital medicine compared to other specialties which is that there is simply too much out there.
The plain truth is unfortunately that we will never have time to read everything.
I truly wish we could but unfortunately we can't. 
My original question of "How do I read it all?" has been reframed to "how do I stay generally aware of what's going on without
it consuming my whole life?"


### Current options

One option would be to subscribe to a few journals. The problem is that the journals
with the best research and the highest probability of changing practice such as NEJM and 
JAMA are not specific to hospital medicine. A huge fraction of what they publish is simply
out of scope. By the same token, they are not comprehensive either. Finally, they publish a lot of other content, such as editorials, 
letters, and perspectives — which while interesting and important, are not really what I'm looking for. 

Another option would be attending annual hospitalist conferences. 
That works to some degree, but it unfortunately does not feel like enough. By some estimates, over 100 RCTs are published daily. 
Conferences can't keep up with that pace.

Another option would be to follow podcasts/blogs/newsletters. 
These are great options and basically what I have been doing up until now and what I will continue to do. 
They seem to have exploded in popularity, and for good reason — they genuinely improve signal-to-noise. 
But they have some limitations. First, very few are targeted at hospitalists. Some of the internal medicine and critical
care focused, which gets close, but none have been quite the thing I'm looking for. Second, they are all built around curation and commentary.
It makes them super interesting and I appreciate/love that. But that same commentary is riddled with
bias, by necessity, both in what they choose to discuss and how they discuss it. They're all ultimately trying to answer one "simple" question:
Does this paper change my practice? To answer it, they critique the paper — both favorably and unfavorably, conduct interviews, 
and try to place it in context, against the existing literature and against feasibility in the real world. This is what we should be doing,
but unfortunately by doing this, each article/concept takes more of our time, and we then have less time for the next one. 
If the topic doesn't engage us, we are almost happy. We get to skip that episode and do something else.

The question "Does this change my practice?" is not "simple" at all. Two experts can
read the exact same paper and walk away with completely opposite conclusions. So then what
do you do? This central question most often does not lead anywhere clean. Every patient
and every situation is a little different. And if the burden is on *me* to deeply analyze
every paper, then we're right back in the fantasy land of infinite time, no hobbies, no
responsibilities outside of work, and no burnout. 

### What I would like to see

Like everyone else, I want to optimize signal-to-noise. However, noise is really difficult to filter out because everyone has different perspectives.
So I want to err on the side of more signal. I also want to optimize time. I don't feel optimizing time is thought about as much, but in my opinion,
when you incorporate time into the framework, it becomes a three-body-problem with no excellent solution.

To optimize time, here are some leave-outs I've decided to make:

- No commentary. If something genuinely grabs my interest, I can go find the commentary myself.
But for topics that don't grab my attention, I still want to know a little about them.
- No worries about the whole paper. For example, for now, I don't care whether a drug company funded a trial. That is for a deep dive day.
I really just want to know the key points in the abstracts. I know that abstracts lie, but for now, it is what it is.
I want unscreened abstracts to get 5–10 seconds of my precious time.

### PubMed works for this

A PubMed workflow for this starts out simple. Save a search that
included every journal and filter I care about, run it
periodically, and save the articles I liked into PubMed's own collections.
Conceptually, I was fine with this. But in execution, it's tougher than I would really like it to be.
There is too much on the page, too many clicks, and organization isn't excellent. Overall, I would say it may not sound like much.
But once I made my alternative, I liked it much better.

### My program/process

I'm happy to share the code with anybody - just ask. Drop me a note
through the "Suggest an article" page in the sidebar and it'll reach me. I'm also happy to work with you if you want to set up a 
personal version for yourself with your own filters.

Basically, the program on the back-end does the following: it pulls a list of only trials and systematic reviews published across 50+ journals I
care about. It then lets me triage fast based on title, whether I want to read the abstract, or mark it irrelevant so I never see
it again. I then read the abstracts, and if I want to save it, I add it to my database. 

The app does some other small things like split the abstract into a more digestible form built for rapid reading. Because there's no single stable abstract
format across all these journals, there's a little AI involved here — which means there's some risk of inaccuracy. 
However, I do ask the AI to always reproduce the author's conclusion verbatim. Having the abstracts in my database also allows for easy searching, sorting, and categorizing. 
I also pull related articles based on PubMed's "Similar articles" list
(top 5) and Semantic Scholar's. On the public-facing side, all you see is the database of abstracts. From any study you can
jump straight to PubMed, or open a separate page inside the app with the extracted details.
Right now you can sort by year, by specialty, and by date added.

The main caveats are 3-fold: First, I already touched on, is that some AI is involved. Ideally I would go over the extracted information and edit it.
My app lets me do that. But to be honest in this development phase I haven't done that much at all. I may go back and clean up extracted information later. 
However, the full abstracts are available in the database so you can always read the source if something looks off. Second, what ends up in the database
may reflect my bias. I generally make decisions rapidly based on topic, type of study, number of patients, quality of journal, and findings. 
Regarding topic and conclusions, sometimes I'll not include a paper if the topic is saturated already within the database, 
if the conclusion is too antithetical to current practice, if the trial is a negative study of a new intervention, or if the trial is a positive study of an intervention that is already widely used.
I am sure I have some other biases as well. Unfortunately this is unavoidable and I am hoping that I can do a good job of being self-aware about it. I also hope that
at some point the "Suggest an article" page gets some good usage to help combat that and help me find blind spots. . Third, it has to be used for what it's meant to be:
not a point-of-care tool or a deep-dive tool, but a screening tool that you can spend 5 minutes on whenever you have a little time or interest.
Fourth and finally, things might change or even break as I continue to work on it. Once again, if anyone has ideas, or spots something
broken, I would love to hear about it.

### Guidelines

In addition to trials and systematic reviews, I have also incorporated guidelines into the app. The main problem I'm trying to address here, 
besides the breadth problem that I discussed above, is that guidelines are often written in a way that is very difficult to read. On the other hand,
full-text guidelines are usually free to access in pdf form.

I lean a little more into AI for this part. I do the following: I upload the pdf. 
Then, the app reads the text out and extracts a list of recommendations and organizes them into categories. 
I can clean up the output before it goes live, but again, I haven't done much of that yet.
I like where I'm at currently and do think it is very useful. The app has helped me read a lot more guidelines than I used to.
However, overall there are a number of technical challenges with working with guidelines and so it's not as perfect as I would like it to be yet.

"""


def render() -> None:
    st.title("ℹ️ About")
    st.markdown(_ABOUT_MD)
