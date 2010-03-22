#!/usr/bin/python
import nltk
import re

import AGFL
from tokenizer import word_tokenize, word_detokenize


# These tend to be pretty solid.
class AGFLTweaker:
  nltk_ep4_map = {
    "PRP$" : "POSSPRON", # pronoun, possessive
    "RB" : "ADVB(modf)", # adverb
    "RBR" : "ADVB(comp)", # adverb, comparative
    "RBS" : "ADVB(supl)", # adverb, superlative
    "RP" : "PARTICLE(none)", # particle. XXX: these next 4 should have the word?
    "JJ" : "ADJE(abso,none)", # adjective or numeral, ordinal 
    "JJR" : "ADJE(comp,none)", # adjective, comparative
    "JJS" : "ADJE(supl,none)", # adjective, superlative
    "CC" : "CON(coo)", # conjunction, coordinating
    "IN" : "CON(sub)", # preposition or conjunction, subordinating
    "UH" : "INTERJ", # interjection
    "CD" : "NUM(card)", # numeral, cardinal
    "." : "-."
  }

  # These tags tend not to work very well with NLTK.
  # Leave them (and others) as their NLTK equivs to
  # let the HMM compensate a bit using context. Left here
  # for reference.
  nltk_ep4_map_junky = {
    # NLTK is too generous with tagging things as nouns
    "NN" : "NOUN(sing)", # noun, common, singular or mass
    "NNP" : "NOUN(sing)", # noun, proper, singular
    "NNPS" : "NOUN(plur)", # noun, proper, plural
    "NNS" : "NOUN(plur)", # noun, common, plural

    # These need some review..
    "VB" : "VERBI(NONE,none,cplx)", # verb, base form
    "VBD" : "VERBP(NONE,none,cplx)", # verb, past tense
    "VBG" : "VERBG(NONE,none,cplx)", # verb, present participle or gerund
    "VBN" : "VERBP(NONE,none,trav)", # verb, past participle
    "VBP" : "VERBV(NONE,none,cplx)", # verb, present tense, not 3rd person singular
    "VBZ" : "VERBS(None,none,cplx)",# verb, present tense, 3rd person singular
    "PRP" : "PERSPRON(nltk,nltk,nltk)" # pronoun, personal
  }

  # Temporarily strip out stuff we left in (esp for AGFL)
  def agfl_fix(self, tokens, nltk_tags):
    fixed = False
    for t in xrange(len(nltk_tags)):
      tokens[t] = re.sub(r"\.\.[\.]+", "...", tokens[t])
      if nltk_tags[t][0] == "'s":
        # FIXME: Add to normalizer/undo?
        if nltk_tags[t][1] == "VBZ":
          tokens[t] = "is"
        elif nltk_tags[t][1] == "POS": # Evil Hack. XXX: Undo?
          tokens[t-1] += "s"
          nltk_tags[t-1] = (nltk_tags[t-1][0]+"s", nltk_tags[t-1][1])
          fixed = True
    if fixed:
      nltk_tags.remove(("'s", "POS"))
      tokens.remove("'s")

  # FIXME: Can we do anything clever with "!1!1!1" and "?//?/1!/"?
  # AGFL also hates ".."
  # FIXME: This needs context...
  bad_affix = ["^[\#\@\']", "[\']$"]
  replace = ["^[\/\*\']", "[\/\*\']$"] # => ""
  def __init__(self):
    self.sub_map = {}

  # TODO: ["[a-z]/[a-z]"] => " or "
  def prune(self, tags):
    for i in xrange(len(tags)):
      for r in self.bad_affix:
        s = re.sub(r, "", tags[i])
        if s != tags[i]:
          self.sub_map[s] = tags[i]
          tags[i] = s
      for r in self.replace:
        # Don't bother to record replaced text..
        s = re.sub(r, "", tags[i])
        if s != tags[i]:
          tags[i] = s
    return tags

  def deprune(self, pos_tags):
    for i in xrange(len(pos_tags)):
      if pos_tags[i][0] in self.sub_map:
        pos_tags[i] = (self.sub_map[pos_tags[i][0]], pos_tags[i][1])
    return pos_tags

  def tag_vote(self, tags):
    # Noun, then verb, then adj/adv
    # Take majority of the tags
    vote_map = {}
    for t in tags:
      if not t: continue
      if "NOUN" in t: return t
      if t not in vote_map: vote_map[t] = 0
      vote_map[t] += 1

    for t in tags:
      if "VERB" in t: return t
    for t in tags:
      if "ADJ" in t: return t
    for t in tags:
      if "ADV" in t: return t

    max_key = None
    for t in vote_map.iterkeys():
      if not max_key: max_key = t
      if vote_map[t] > vote_map[max_key]:
        max_key = t

    if max_key: return max_key
    else: return ""

  def agfl_split(self, agfl_tags):
    new_agfl_tags = []
    for i in xrange(len(agfl_tags)):
      if not agfl_tags[i][1]:
        # Split it.
        toks = word_tokenize(agfl_tags[i][0])
        for i in toks: new_agfl_tags.append((i, ""))
      else:
        new_agfl_tags.append(agfl_tags[i])
    return new_agfl_tags

  def agfl_join(self, agfl_tags, tokens):
    # AGFL can join or split words/urls. Rejoin split ones.
    offset = 0
    did_replace = False
    for n in xrange(len(tokens)-1):
      if n-offset >= len(agfl_tags): break
      word_chunk = agfl_tags[n-offset][0]
      tags_joined = [agfl_tags[n-offset][1]]
      add = (len(agfl_tags[n-offset][0].split())-1)
      for a in xrange(n+1-offset, len(agfl_tags)):
        tags_joined.append(agfl_tags[a][1])
        word_chunk += agfl_tags[a][0]
        if tokens[n] == word_chunk:
          for i in xrange(n-offset,a+1-offset): agfl_tags.pop(n-offset)
          tag = (word_chunk, self.tag_vote(tags_joined))
          agfl_tags.insert(a-1, tag)
          did_replace = True
          break
      offset += add
    return did_replace

  def agfl_repair(self, agfl_tags, nltk_tags):
    # This is somewhat hackish
    # XXX: Agfl will lowercase some words!. Esp "I"
    for a in xrange(len(agfl_tags)):
      if not agfl_tags[a][1] or agfl_tags[a][1] == "WORD" or \
            agfl_tags[a][1].isspace():
        closest = -1
        for n in xrange(len(nltk_tags)):
          if agfl_tags[a][0] == nltk_tags[n][0]:
            if closest > 0:
              print "Two tags found for "+agfl_tags[a][0]
              if abs(a-n) > abs(a-closest):
                continue # Farther away. Skip
            closest = n
            if nltk_tags[n][1] in self.nltk_ep4_map:
              agfl_tags[a] = (nltk_tags[n][0],
                                self.nltk_ep4_map[nltk_tags[n][1]])
            else:
              #print nltk_tags[n][1]+" not in nltk map!"
              agfl_tags[a] = (nltk_tags[n][0], nltk_tags[n][1])
    return agfl_tags

agfl = AGFL.AGFLWrapper()
# XXX: Maybe rewrite tweaker.prune() to be
# position aware. Then we can stop doing quite
# so many calls to word_detokenize()
def pos_tag(tokens):
  if agfl.agfl_ok():
    detoked = word_detokenize(tokens)
    sentences = nltk.sent_tokenize(detoked)
    all_tags = []
    for s in sentences:
      stokens = word_tokenize(s)
      nltk_tags = nltk.pos_tag(stokens)
      tweaker = AGFLTweaker()
      tweaker.agfl_fix(stokens, nltk_tags)
      tweaker.prune(stokens)
      s = word_detokenize(stokens)
      if not s:
        print "Empty string for: "+str(stokens)
        continue
      #print "Parsing: |"+s+"|"
      agfl_tree = agfl.parse_sentence(s)
      if not agfl_tree:
        print "Parse fail for |"+s+"|"
        return None # Hrmm. use partials? Prob not
      else:
        tags = agfl_tree.pos_tag()
        tags = tweaker.agfl_split(tags)
        did_join = tweaker.agfl_join(tags, stokens)
        tweaker.deprune(tags)
        tweaker.agfl_repair(tags, nltk_tags)
        # Verify that we have labels for everything.
        # If some are still missing, drop.
        if tags:
          for t in tags:
            if not t[1]:
              print "Tag fail for: |"+s+"|"
              print str(tags)
              if did_join: print "Failed with attempted join: "+str(stokens)
              return None
          all_tags.extend(tags)
        else:
          print "Tag fail for |"+s+"|"
          return None
    return all_tags
  else:
    # XXX: Kill this log
    print "AGFL not found/functional. Fallig back to nltk.pos_tag()"
    return nltk.pos_tag(tokens)


def main():
  tweaker = AGFLTweaker()
  toks = word_tokenize("@John I am goin' to the #store, *catfeesh*?")
  tweaker.prune(toks)
  print toks
  tweaker.deprune(toks)
  print toks
  print pos_tag(word_tokenize("@John, I am going to the #store. Will you #come with me?"))

if __name__ == "__main__":
   main()
