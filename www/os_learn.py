# import os
# path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')  # os模块用的不熟
# print(os.path.abspath(__file__))  # /Users/gonghuidepro/PycharmProjects/awesome-python3-webapp/www/os_learn.py
#
# print(os.path.dirname(os.path.abspath(__file__)))
# # /Users/gonghuidepro/PycharmProjects/awesome-python3-webapp/www
#
# print(path)
# # /Users/gonghuidepro/PycharmProjects/awesome-python3-webapp/www/templates


class SayMetaClass(type):
    def __new__(cls, name, bases, attrs):
        attrs['say_'+name] = lambda self, value, saying=name: print(saying + ',' + value + '!')
        return type.__new__(cls, name, bases, attrs)


class Hello(object, metaclass=SayMetaClass):
    pass


he = Hello()

he.say_Hello('world')


class Sayanala(object, metaclass=SayMetaClass):
    pass

sa = Sayanala()
sa.say_Sayanala('Japan')


class ListMetaClass(type):
    def __new__(cls, name, bases, attrs):
        attrs['add'] = lambda self, value: self.append(value)
        return type.__new__(cls, name, bases, attrs)


class MyList(list, metaclass=ListMetaClass):
    pass


m = MyList()
m.add('asdd')

print(m)
print(m.__dir__())





































































