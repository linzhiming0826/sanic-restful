


## Sanic-Restful-Api

### Simple framework for creating REST APIs

## Introduce

After writing Sanic for a long time, I found that there was no framework similar to flask-restful, so I wrote one myself.

[flask-restful](https://github.com/flask-restful/flask-restful)

## Document

[click me](https://sanic-restful-api.readthedocs.io/)

## Installation
```linux
pip install sanic-restful-api
```

## Simple uses
```python
from sanic import Sanic
from sanic_restful_api import reqparse, abort, Api, Resource

app = Sanic(__name__)
api = Api(app)

TODOS = {
    'todo1': {'task': 'build an API'},
    'todo2': {'task': '?????'},
    'todo3': {'task': 'profit!'},
}


def abort_if_todo_doesnt_exist(todo_id):
    if todo_id not in TODOS:
        abort(404, message="Todo {} doesn't exist".format(todo_id))


parser = reqparse.RequestParser()
parser.add_argument('task')

# Todo
#   show a single todo item and lets you delete them


class Todo(Resource):
    async def get(self, request, todo_id):
        abort_if_todo_doesnt_exist(todo_id)
        return TODOS[todo_id]

    async def delete(self, request, todo_id):
        abort_if_todo_doesnt_exist(todo_id)
        del TODOS[todo_id]
        return '', 204

    async def put(self, request, todo_id):
        args = parser.parse_args(request)
        task = {'task': args['task']}
        TODOS[todo_id] = task
        return task, 201


# TodoList
#   shows a list of all todos, and lets you POST to add new tasks
class TodoList(Resource):
    async def get(self, request):
        return TODOS

    async def post(self, request):
        args = parser.parse_args(request)
        todo_id = 'todo%d' % (len(TODOS) + 1)
        TODOS[todo_id] = {'task': args['task']}
        return TODOS[todo_id], 201


##
# Actually setup the Api resource routing here
##
api.add_resource(TodoList, '/todos')
api.add_resource(Todo, '/todos/<string:todo_id>')


if __name__ == '__main__':
    app.run(debug=True)
```