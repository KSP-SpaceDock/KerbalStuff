editor = new Editor()
editor.render()

window.upload_bg = (files, box) ->
    file = files[0]
    p = document.createElement('p')
    p.textContent = 'Uploading...'
    p.className = 'status'
    box.appendChild(p)
    box.querySelector('a').classList.add('hidden')
    progress = box.querySelector('.upload-progress')

    xhr = new XMLHttpRequest()
    xhr.open('POST', "/api/mod/#{window.mod_id}/update-bg")
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (e) ->
        if e.lengthComputable
            progress.style.width = (e.loaded / e.total) * 100 + '%'
    xhr.onload = (e) ->
        if xhr.status != 200
            p.textContent = 'Please upload JPG or PNG only.'
            setTimeout(() ->
                box.removeChild(p)
                box.querySelector('a').classList.remove('hidden')
            , 3000)
        else
            resp = JSON.parse(xhr.responseText)
            p.textContent = 'Done!'
            document.getElementById('header-well').style.backgroundImage = 'url("' + resp.path + '")'
            setTimeout(() ->
                box.removeChild(p)
                box.querySelector('a').classList.remove('hidden')
            , 3000)
    formdata = new FormData()
    formdata.append('image', file)
    xhr.send(formdata)

document.getElementById('add-shared-author').addEventListener('click', (e) ->
    e.preventDefault()
    m = document.getElementById('shared-author-error')
    u = document.getElementById("new-shared-author")
    m.classList.add('hidden')
    xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/mod/' + window.mod_id + '/grant')
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.onload = () ->
        response = JSON.parse(this.responseText)
        if response.error
            m.textContent = response.message
            m.classList.remove('hidden')
        else
            div = document.createElement('div')
            div.className = 'col-md-6'
            div.textContent = u.value
            b = document.getElementById('beforeme')
            b.parentElement.insertBefore(div, b)
            u.value = ''
    data = new FormData()
    data.append('user', u.value)
    xhr.send(data)
, false)

document.getElementById('new-shared-author').addEventListener('keypress', (e) ->
    if e.keyCode == 13
        e.preventDefault()
        document.getElementById('add-shared-author').click()
, false)

a.addEventListener('click', (e) ->
    e.preventDefault()
    target = e.target
    if target.tagName != 'A'
        target = target.parentElement
    xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/mod/' + window.mod_id + '/revoke')
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.onload = () ->
        window.location = window.location
    form = new FormData()
    form.append('user', target.dataset.user)
    xhr.send(form)
, false) for a in document.querySelectorAll('.remove-author')
