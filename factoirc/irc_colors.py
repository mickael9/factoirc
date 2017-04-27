__all__ = ['IRCColors']


class IRCColors:
    """Provide composition of IRC control codes via attribute access.

    Attributes can be a concatenation of up to three parts (case is ignored):
        - A control code (bold, reverse, etc).
        - A foreground color name
        - A background color name

    For instance:
        - "Bold" will toggle bold
        - "BoldRed" will toggle bold and set color to red
        - "BoldGreenRed" will toggle bold, set foreground color to green
           and set background color to red
    """

    COLOR_NAMES = dict(
        white='00',
        black='01',
        blue='02',
        green='03',
        red='04',
        brown='05',
        purple='06',
        orange='07',
        yellow='08',
        ltgreen='09',
        teal='10',
        cyan='11',
        ltblue='12',
        pink='13',
        grey='14',
        ltgrey='15',
        default='99',
    )

    CONTROL_CODES = dict(
        bold='\x02',
        color='\x03',
        italic='\x1D',
        underline='\x1F',
        reverse='\x16',
        reset='\x0F'
    )

    def __getattr__(self, tags):
        cur_tags = tags.lower()
        result = ''

        for code_name, code in self.CONTROL_CODES.items():
            if cur_tags.startswith(code_name):
                result += code
                cur_tags = cur_tags[len(code_name):]
                break

        if result and not cur_tags:
            return result

        result += self.CONTROL_CODES['color']

        for prefix in ('', ','):
            for color_name, color_code in self.COLOR_NAMES.items():
                if cur_tags.startswith(color_name):
                    result += prefix + color_code
                    cur_tags = cur_tags[len(color_name):]
                    break

        if cur_tags:
            raise AttributeError(tags)

        return result


IRCColors = IRCColors()
