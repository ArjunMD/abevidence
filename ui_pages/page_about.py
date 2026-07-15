import streamlit as st

_ABOUT_MD = """
- This website is a collection of abstracts that I find useful for hospital medicine.
- It is a personal tool that I wanted access to from anywhere, so I put it on the internet.
- As far as I know, there is no other single place to find all the high-impact RCTs and systematic reviews that are specifically relevant to hospital medicine.
- Of course, I don't make any claims about comprehensiveness.
- AI is used to extract structured information from the abstracts to facilitate rapid reading.
- There is no commentary on or critique of the studies. I am still considering including funding information.
- Essentially, the goal is for this to be a fun place to spend 5 minutes at a time browsing.
- I would love it if people used the "Suggest an article" page to send me articles that they think are important and relevant to hospital medicine, particularly if they are in a blind spot not represented by the current database.
- Within a single-study view, don't forget to check out the "Similar articles" sections.
- In addition to trials and systematic reviews, guidelines are also included.
- AI is used to extract structured information from the guidelines to facilitate rapid reading, but context is slightly lost and therefore it's a good idea to go to the original guideline for that, but as a starting point, this website is useful.
- I would love any feedback! Simply type something in the "Suggest an article" page.
- Thank you for visiting!

"""


def render() -> None:
    st.title("ℹ️ About")
    st.markdown(_ABOUT_MD)
