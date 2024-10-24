import os, re
import random
from PIL import Image, ImageDraw, ImageFont
import datetime
from fontTools.ttLib import TTFont
import uuid

class cover_image:
    def generate_image(self,base_dir,title, topText, author, image_code, theme, guide_text_placement='bottom_right', guide_text='The Definitive Guide'):

        themeColors = {
            "0" : (85,19,93,255),
            "1" : (113,112,110,255),
            "2" : (128,27,42,255),
            "3" : (184,7,33,255),
            "4" : (101,22,28,255),
            "5" : (80,61,189,255),
            "6" : (225,17,5,255),
            "7" : (6,123,176,255),
            "8" : (247,181,0,255),
            "9" : (0,15,118,255),
            "10" : (168,0,155,255),
            "11" : (0,132,69,255),
            "12" : (0,153,157,255),
            "13" : (1,66,132,255),
            "14" : (177,0,52,255),
            "15" : (55,142,25,255),
            "16" : (133,152,0,255),
        }
        themeColor = themeColors[theme]

        width = 500
        height = 700
        im = Image.new('RGBA', (width, height), "white")

        font_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'fonts', 'GaramondLight.ttf'))
        font_path_helv = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'fonts', 'HelveticaNeue-Medium.otf'))
        font_path_helv_bold = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'fonts', 'HelveticaBold.ttf'))
        font_path_italic = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'fonts', 'GaramondLightItalic.ttf'))
        topFont = ImageFont.truetype(font_path_italic, 20)
        subtitleFont = ImageFont.truetype(font_path_italic, 34)
        authorFont = ImageFont.truetype(font_path_italic, 12)
        titleFont = ImageFont.truetype(font_path, 62)
        oriellyFont = ImageFont.truetype(font_path_helv, 14)
        questionMarkFont = ImageFont.truetype(font_path_helv_bold, 16)

        dr = ImageDraw.Draw(im)
        dr.rectangle(((20,0),(width-20,10)), fill=themeColor)

        topText = self.sanitzie_unicode(topText, font_path_italic)
        bbox = dr.textbbox((0, 0), topText, font=topFont)
        textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]

        textPositionX = (width/2) - (textWidth/2)

        dr.text((textPositionX,10), topText, fill='black', font=topFont)

        author = self.sanitzie_unicode(author, font_path_italic)

        bbox = dr.textbbox((0, 0), author, font=authorFont)
        textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
        textPositionX = width - textWidth - 20
        textPositionY = height - textHeight - 20

        dr.text((textPositionX,textPositionY), author, fill='black', font=authorFont)

        oreillyText = "O RLY"

        bbox = dr.textbbox((0, 0), oreillyText, font=oriellyFont)
        textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]

        textPositionX = 20
        textPositionY = height - textHeight - 20

        dr.text((textPositionX,textPositionY), oreillyText, fill='black', font=oriellyFont)

        oreillyText = "?"

        textPositionX = textPositionX + textWidth

        dr.text((textPositionX,textPositionY-1), oreillyText, fill=themeColor, font=questionMarkFont)
        titleFont, newTitle = self.clamp_title_text(self.sanitzie_unicode(title, font_path), width-80)
        if newTitle == None:
            raise ValueError('Title too long')

        bbox = dr.multiline_textbbox((0, 0), newTitle, font=titleFont)
        textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]


        dr.rectangle([(20,400),(width-20,400 + textHeight + 40)], fill=themeColor)

        subtitle = self.sanitzie_unicode(guide_text, font_path_italic)

        if guide_text_placement == 'top_left':
            bbox = dr.textbbox((0, 0), subtitle, font=subtitleFont)
            textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]
            textPositionX = 20
            textPositionY = 400 - textHeight - 2
        elif guide_text_placement == 'top_right':
            bbox = dr.textbbox((0, 0), subtitle, font=subtitleFont)
            textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]
            textPositionX = width - 20 - textWidth
            textPositionY = 400 - textHeight - 2
        elif guide_text_placement == 'bottom_left':
            textPositionY = 400 + textHeight + 40
            bbox = dr.textbbox((0, 0), subtitle, font=subtitleFont)
            textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]
            textPositionX = 20
        else:#bottom_right is default
            textPositionY = 400 + textHeight + 40
            bbox = dr.textbbox((0, 0), subtitle, font=subtitleFont)
            textWidth, textHeight = bbox[2] - bbox[0], bbox[3] - bbox[1]
            textPositionX = width - 20 - textWidth

        dr.text((textPositionX,textPositionY), subtitle, fill='black', font=subtitleFont)

        dr.multiline_text((40,420), newTitle, fill='white', font=titleFont)

        cover_image_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ),  '..','images', ('%s.png'%image_code)))
        coverImage = Image.open(cover_image_path).convert('RGBA')

        offset = (80,40)
        im.paste(coverImage, offset, coverImage)
        final_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..',base_dir,('%s.png'%uuid.uuid4())))
        #final_path=os.path.join(base_dir,('%s.png'%uuid.uuid4()))
        im.save(final_path)
        im.close()

        im = Image.open(final_path)
        fig = im.convert('RGB')
        final_path = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..',base_dir,('%s.eps'%uuid.uuid4())))
        #final_path=os.path.join(base_dir,('%s.eps'%uuid.uuid4()))
        fig.save(final_path,lossless = True)
        im.close()
        fig.close()

        return final_path

    def clamp_title_text(self,title, width):
        im = Image.new('RGBA', (500,500), "white")
        dr = ImageDraw.Draw(im)

        font_path_italic = os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..', 'fonts', 'GaramondLight.ttf'))
        #try and fit title on one line
        font = None

        startFontSize = 80
        endFontSize = 61

        for fontSize in range(startFontSize,endFontSize,-1):
            font = ImageFont.truetype(font_path_italic, fontSize)
            bbox = dr.textbbox((0, 0), title, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

            if w < width:
                return font, title

        #try and fit title on two lines
        startFontSize = 80
        endFontSize = 34

        for fontSize in range(startFontSize,endFontSize,-1):
            font = ImageFont.truetype(font_path_italic, fontSize)

            for match in list(re.finditer(r'\s',title, re.UNICODE)):
                newTitle = u''.join((title[:match.start()], u'\n', title[(match.start()+1):]))
                bbox = dr.multiline_textbbox((0, 0), newTitle, font=font)
                substringWidth, h = bbox[2] - bbox[0], bbox[3] - bbox[1]


                if substringWidth < width:
                    return font, newTitle

        im.close()

        return None, None

    def sanitzie_unicode(self,string, font_file_path):
        sanitized_string = u''

        font = TTFont(font_file_path)
        cmap = font['cmap'].getcmap(3,1).cmap
        for char in string:
            code_point = ord(char)

            if code_point in cmap.keys():
                sanitized_string = ''.join((sanitized_string, char))

        return sanitized_string

def main():
    ci = cover_image()
    result=ci.generate_image(
        "Dify Guide", 
        "NowCode", 
        "Tomatio",  
        "3", 
        "6", 
        'bottom_right', 
        'The Definitive Guide'
    )
    print(result)
    
if __name__ == "__main__":
    main()